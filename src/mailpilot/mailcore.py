"""Mail engine: IMAP, POP3, SMTP, message parsing and search.

Uses only the Python standard library. This module never imports tkinter,
so it can be tested without a display.
"""
from __future__ import annotations

import base64
import datetime as dt
import email
import imaplib
import mimetypes
import poplib
import re
import shlex
import smtplib
import ssl
from dataclasses import dataclass, field
from email import policy
from email.message import EmailMessage
from email.utils import formatdate, getaddresses, make_msgid, parseaddr, parsedate_to_datetime
from html.parser import HTMLParser
from typing import List, Optional, Tuple

TIMEOUT = 30
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


class MailError(Exception):
    """A problem that can be shown to the user in plain language."""


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------
def imap_date(d: dt.date) -> str:
    return f"{d.day:02d}-{MONTHS[d.month - 1]}-{d.year}"


def imap_utf7_decode(s: str) -> str:
    def repl(m):
        b64 = m.group(1)
        if b64 == "":
            return "&"
        b64 = b64.replace(",", "/")
        b64 += "=" * (-len(b64) % 4)
        return base64.b64decode(b64).decode("utf-16-be")
    return re.sub(r"&([^-]*)-", repl, s)


def imap_utf7_encode(s: str) -> str:
    out, buf = [], ""

    def flush():
        nonlocal buf
        if buf:
            b = base64.b64encode(buf.encode("utf-16-be")).decode().rstrip("=").replace("/", ",")
            out.append("&" + b + "-")
            buf = ""

    for ch in s:
        if 0x20 <= ord(ch) <= 0x7E:
            flush()
            out.append("&-" if ch == "&" else ch)
        else:
            buf += ch
    flush()
    return "".join(out)


def imap_quote(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


class _TextExtractor(HTMLParser):
    BLOCK = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6", "table", "blockquote"}
    SKIP = {"script", "style", "head", "title"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    """Strip HTML to plain text. Nothing is rendered, so scripts and remote images never load."""
    p = _TextExtractor()
    try:
        p.feed(html)
        p.close()
    except Exception:
        pass
    text = "".join(p.parts)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# --------------------------------------------------------------------------
# data classes
# --------------------------------------------------------------------------
@dataclass
class Folder:
    name: str        # raw (encoded) name used in IMAP commands
    display: str     # human readable


@dataclass
class MsgHeader:
    uid: str
    sender: str = ""
    subject: str = ""
    date: str = ""
    unread: bool = False


@dataclass
class Attachment:
    index: int
    filename: str
    content_type: str
    size: int


@dataclass
class ParsedMessage:
    subject: str = ""
    sender: str = ""
    to: str = ""
    cc: str = ""
    date: str = ""
    message_id: str = ""
    references: str = ""
    reply_to: str = ""
    body: str = ""
    attachments: List[Attachment] = field(default_factory=list)
    raw: bytes = b""


@dataclass
class SearchQuery:
    from_: str = ""
    to: str = ""
    subject: str = ""
    text: str = ""
    since: Optional[dt.date] = None
    before: Optional[dt.date] = None
    unread: bool = False
    has_attachment: bool = False
    all_folders: bool = False

    def is_empty(self) -> bool:
        return not any([self.from_, self.to, self.subject, self.text, self.since,
                        self.before, self.unread, self.has_attachment])


# --------------------------------------------------------------------------
# search query text  ->  SearchQuery  ->  IMAP criteria
# --------------------------------------------------------------------------
def _parse_date(s: str) -> Optional[dt.date]:
    try:
        return dt.date.fromisoformat(s)
    except ValueError:
        return None


def parse_query_text(s: str) -> SearchQuery:
    """Parse the search box.

    Example: from:ali subject:"fee invoice" unread has:attachment since:2026-11-01 budget
    Words without a prefix search the whole message text.
    """
    q = SearchQuery()
    try:
        tokens = shlex.split(s)
    except ValueError:
        tokens = s.split()
    free: List[str] = []
    for tok in tokens:
        low = tok.lower()
        if ":" in tok:
            key, _, val = tok.partition(":")
            key = key.lower()
            if key == "from":
                q.from_ = val; continue
            if key == "to":
                q.to = val; continue
            if key == "subject":
                q.subject = val; continue
            if key == "since":
                q.since = _parse_date(val); continue
            if key == "before":
                q.before = _parse_date(val); continue
            if key == "has" and val.lower() == "attachment":
                q.has_attachment = True; continue
            if key == "in" and val.lower() == "all":
                q.all_folders = True; continue
        if low in ("unread", "is:unread"):
            q.unread = True
        else:
            free.append(tok)
    q.text = " ".join(free)
    return q


def build_imap_search(q: SearchQuery) -> Tuple[Optional[str], List[str]]:
    """Return (charset, criteria). charset is 'UTF-8' only when needed."""
    c: List[str] = []
    values = [q.from_, q.to, q.subject, q.text]
    if q.from_:
        c += ["FROM", imap_quote(q.from_)]
    if q.to:
        c += ["TO", imap_quote(q.to)]
    if q.subject:
        c += ["SUBJECT", imap_quote(q.subject)]
    if q.text:
        c += ["TEXT", imap_quote(q.text)]
    if q.since:
        c += ["SINCE", imap_date(q.since)]
    if q.before:
        c += ["BEFORE", imap_date(q.before)]
    if q.unread:
        c += ["UNSEEN"]
    if q.has_attachment:
        c += ["HEADER", "Content-Type", imap_quote("multipart/mixed")]  # heuristic
    if not c:
        c = ["ALL"]
    charset = "UTF-8" if any(not v.isascii() for v in values if v) else None
    return charset, c


def _matches_local(h: MsgHeader, q: SearchQuery) -> bool:
    """Client-side filter used for POP3 (headers only)."""
    if q.from_ and q.from_.lower() not in h.sender.lower():
        return False
    if q.subject and q.subject.lower() not in h.subject.lower():
        return False
    if q.text and q.text.lower() not in (h.subject + " " + h.sender).lower():
        return False
    if q.unread and not h.unread:
        return False
    return True


# --------------------------------------------------------------------------
# parsing
# --------------------------------------------------------------------------
def _fmt_date(value: str) -> str:
    if not value:
        return ""
    try:
        d = parsedate_to_datetime(value)
        if d.tzinfo is not None:
            d = d.astimezone()
        return d.strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError, IndexError):
        return value[:25]


def _hdr(msg, name: str) -> str:
    try:
        v = msg[name]
        return str(v).strip() if v is not None else ""
    except Exception:
        return ""


def header_from_bytes(uid: str, raw: bytes, unread: bool = False) -> MsgHeader:
    m = email.message_from_bytes(raw, policy=policy.default)
    return MsgHeader(uid=uid, sender=_hdr(m, "From"), subject=_hdr(m, "Subject") or "(no subject)",
                     date=_fmt_date(_hdr(m, "Date")), unread=unread)


def parse_message(raw: bytes) -> ParsedMessage:
    msg = email.message_from_bytes(raw, policy=policy.default)
    pm = ParsedMessage(
        subject=_hdr(msg, "Subject") or "(no subject)",
        sender=_hdr(msg, "From"), to=_hdr(msg, "To"), cc=_hdr(msg, "Cc"),
        date=_fmt_date(_hdr(msg, "Date")), message_id=_hdr(msg, "Message-ID"),
        references=_hdr(msg, "References"), reply_to=_hdr(msg, "Reply-To"), raw=raw,
    )
    body = ""
    try:
        part = msg.get_body(preferencelist=("plain", "html"))
        if part is not None:
            try:
                body = part.get_content()
            except Exception:  # unknown charset etc.
                payload = part.get_payload(decode=True) or b""
                body = payload.decode("utf-8", errors="replace")
            if part.get_content_type() == "text/html":
                body = html_to_text(body)
    except Exception:
        body = ""
    pm.body = body.strip()
    try:
        for i, part in enumerate(msg.iter_attachments()):
            data = part.get_payload(decode=True) or b""
            pm.attachments.append(Attachment(
                index=i, filename=part.get_filename() or f"attachment-{i + 1}",
                content_type=part.get_content_type(), size=len(data)))
    except Exception:
        pass
    return pm


def attachment_bytes(raw: bytes, index: int) -> Tuple[str, bytes]:
    msg = email.message_from_bytes(raw, policy=policy.default)
    for i, part in enumerate(msg.iter_attachments()):
        if i == index:
            return part.get_filename() or f"attachment-{i + 1}", part.get_payload(decode=True) or b""
    raise MailError("Attachment not found.")


# --------------------------------------------------------------------------
# composing
# --------------------------------------------------------------------------
def reply_subject(subject: str) -> str:
    return subject if re.match(r"^\s*re:", subject, re.I) else "Re: " + subject


def quote_text(pm: ParsedMessage) -> str:
    quoted = "\n".join("> " + line for line in pm.body.splitlines())
    return f"On {pm.date}, {pm.sender} wrote:\n{quoted}"


def build_message(from_addr: str, to: str, subject: str, text: str, html: str = "",
                  cc: str = "", bcc: str = "", in_reply_to: str = "", references: str = "",
                  attachments: Optional[List[str]] = None, from_name: str = "") -> Tuple[EmailMessage, List[str]]:
    """Build the message and the list of envelope recipients (To + Cc + Bcc)."""
    m = EmailMessage()
    m["From"] = f"{from_name} <{from_addr}>" if from_name else from_addr
    m["To"] = to
    if cc:
        m["Cc"] = cc
    m["Subject"] = subject
    m["Date"] = formatdate(localtime=True)
    m["Message-ID"] = make_msgid(domain=from_addr.rsplit("@", 1)[-1] or None)
    if in_reply_to:
        m["In-Reply-To"] = in_reply_to
        m["References"] = (references + " " + in_reply_to).strip()
    m.set_content(text or " ")
    if html:
        m.add_alternative(html, subtype="html")
    for path in attachments or []:
        ctype, enc = mimetypes.guess_type(path)
        maintype, subtype = (ctype or "application/octet-stream").split("/", 1)
        with open(path, "rb") as fh:
            m.add_attachment(fh.read(), maintype=maintype, subtype=subtype,
                             filename=path.replace("\\", "/").rsplit("/", 1)[-1])
    rcpts = [a for _, a in getaddresses([to, cc, bcc]) if a]
    if not rcpts:
        raise MailError("Add at least one valid recipient.")
    return m, rcpts


# --------------------------------------------------------------------------
# sessions
# --------------------------------------------------------------------------
def _ctx() -> ssl.SSLContext:
    return ssl.create_default_context()


class MailSession:
    """Common interface for IMAP and POP3."""
    def folders(self) -> List[Folder]: raise NotImplementedError
    def headers(self, folder: str, page: int, size: int) -> Tuple[List[MsgHeader], int]: raise NotImplementedError
    def message(self, folder: str, uid: str) -> ParsedMessage: raise NotImplementedError
    def search(self, folder: str, q: SearchQuery, size: int) -> List[MsgHeader]: raise NotImplementedError
    def close(self) -> None: pass
    def alive(self) -> bool: return True


class ImapSession(MailSession):
    def __init__(self, host: str, port: int, security: str, user: str, password: str):
        try:
            if security == "ssl":
                self.M = imaplib.IMAP4_SSL(host, port, ssl_context=_ctx(), timeout=TIMEOUT)
            else:
                self.M = imaplib.IMAP4(host, port, timeout=TIMEOUT)
                if security == "starttls":
                    self.M.starttls(ssl_context=_ctx())
            self.M.login(user, password)
        except imaplib.IMAP4.error as e:
            raise MailError("IMAP sign-in failed. Check the address, password or app password. "
                            f"Server said: {_clean(e)}") from None
        except (OSError, ssl.SSLError) as e:
            raise MailError(f"Cannot reach the IMAP server {host}:{port} ({e}).") from None
        self._selected = None

    def alive(self) -> bool:
        try:
            return self.M.noop()[0] == "OK"
        except Exception:
            return False

    def close(self) -> None:
        try:
            self.M.logout()
        except Exception:
            pass

    def folders(self) -> List[Folder]:
        typ, data = self.M.list()
        if typ != "OK":
            raise MailError("Could not list folders.")
        out: List[Folder] = []
        pat = re.compile(rb'\((?P<flags>[^)]*)\)\s+(?:"[^"]*"|NIL)\s+(?P<name>.*)', re.S)
        for item in data:
            if item is None:
                continue
            if isinstance(item, tuple):
                line, name_b = item[0], item[1]
                m = pat.match(line)
                flags = m.group("flags") if m else b""
                name = name_b.decode("utf-8", "replace")
            else:
                m = pat.match(item)
                if not m:
                    continue
                flags = m.group("flags")
                name = m.group("name").decode("utf-8", "replace").strip()
                if name.startswith('"') and name.endswith('"'):
                    name = name[1:-1].replace('\\"', '"').replace("\\\\", "\\")
            if b"\\noselect" in flags.lower():
                continue
            out.append(Folder(name=name, display=imap_utf7_decode(name)))
        out.sort(key=lambda f: (f.display.upper() != "INBOX", f.display.lower()))
        return out

    def _select(self, folder: str, readonly: bool = False) -> int:
        typ, data = self.M.select(imap_quote(folder), readonly=readonly)
        if typ != "OK":
            raise MailError(f"Could not open folder {imap_utf7_decode(folder)}.")
        self._selected = folder
        return int(data[0] or 0)

    def _fetch_headers(self, uids: List[str]) -> List[MsgHeader]:
        if not uids:
            return []
        typ, data = self.M.uid("FETCH", ",".join(uids),
                               "(UID FLAGS BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
        if typ != "OK":
            raise MailError("Could not read message headers.")
        found = {}
        for i, item in enumerate(data):
            if not isinstance(item, tuple):
                continue
            meta = item[0]
            tail = data[i + 1] if i + 1 < len(data) and isinstance(data[i + 1], bytes) else b""
            um = re.search(rb"UID (\d+)", meta) or re.search(rb"UID (\d+)", tail)
            if not um:
                continue
            fm = re.search(rb"FLAGS \(([^)]*)\)", meta) or re.search(rb"FLAGS \(([^)]*)\)", tail)
            seen = bool(fm and b"\\Seen" in fm.group(1))
            uid = um.group(1).decode()
            found[uid] = header_from_bytes(uid, item[1], unread=not seen)
        return [found[u] for u in uids if u in found]

    def headers(self, folder: str, page: int, size: int) -> Tuple[List[MsgHeader], int]:
        self._select(folder)
        typ, data = self.M.uid("SEARCH", None, "ALL")
        if typ != "OK":
            raise MailError("Could not list messages.")
        uids = (data[0] or b"").decode().split()
        total = len(uids)
        newest_first = list(reversed(uids))
        chunk = newest_first[page * size:(page + 1) * size]
        return self._fetch_headers(chunk), total

    def message(self, folder: str, uid: str) -> ParsedMessage:
        if self._selected != folder:
            self._select(folder)
        typ, data = self.M.uid("FETCH", uid, "(BODY.PEEK[])")
        raw = b""
        if typ == "OK":
            for item in data:
                if isinstance(item, tuple):
                    raw = item[1]
                    break
        if not raw:
            raise MailError("Could not download this message.")
        try:
            self.M.uid("STORE", uid, "+FLAGS", "(\\Seen)")
        except Exception:
            pass
        return parse_message(raw)

    def search(self, folder: str, q: SearchQuery, size: int) -> List[MsgHeader]:
        self._select(folder, readonly=True)
        charset, criteria = build_imap_search(q)
        try:
            if charset:
                self.M._encoding = "utf-8"  # needed to send non-ASCII criteria
                typ, data = self.M.uid("SEARCH", "CHARSET", charset, *criteria)
            else:
                typ, data = self.M.uid("SEARCH", None, *criteria)
        except imaplib.IMAP4.error as e:
            raise MailError(f"The server rejected this search: {_clean(e)}") from None
        finally:
            self.M._encoding = "ascii"
        if typ != "OK":
            raise MailError("Search failed.")
        uids = list(reversed((data[0] or b"").decode().split()))[:size]
        return self._fetch_headers(uids)


class Pop3Session(MailSession):
    def __init__(self, host: str, port: int, security: str, user: str, password: str):
        try:
            if security == "ssl":
                self.P = poplib.POP3_SSL(host, port, timeout=TIMEOUT, context=_ctx())
            else:
                self.P = poplib.POP3(host, port, timeout=TIMEOUT)
                if security == "starttls":
                    self.P.stls(context=_ctx())
            self.P.user(user)
            self.P.pass_(password)
        except poplib.error_proto as e:
            raise MailError(f"POP3 sign-in failed. Server said: {_clean(e)}") from None
        except (OSError, ssl.SSLError) as e:
            raise MailError(f"Cannot reach the POP3 server {host}:{port} ({e}).") from None

    def alive(self) -> bool:
        try:
            self.P.noop()
            return True
        except Exception:
            return False

    def close(self) -> None:
        try:
            self.P.quit()
        except Exception:
            pass

    def folders(self) -> List[Folder]:
        return [Folder("INBOX", "Inbox (POP3)")]

    def _top(self, n: int) -> MsgHeader:
        _, lines, _ = self.P.top(n, 0)
        return header_from_bytes(str(n), b"\r\n".join(lines))

    def headers(self, folder: str, page: int, size: int) -> Tuple[List[MsgHeader], int]:
        total = self.P.stat()[0]
        first = total - page * size
        nums = range(first, max(first - size, 0), -1)
        return [self._top(n) for n in nums], total

    def message(self, folder: str, uid: str) -> ParsedMessage:
        _, lines, _ = self.P.retr(int(uid))
        return parse_message(b"\r\n".join(lines))

    def search(self, folder: str, q: SearchQuery, size: int) -> List[MsgHeader]:
        # POP3 has no server search: filter the newest messages' headers locally.
        total = self.P.stat()[0]
        hits: List[MsgHeader] = []
        for n in range(total, 0, -1):
            h = self._top(n)
            if _matches_local(h, q):
                hits.append(h)
            if len(hits) >= size:
                break
        return hits


def open_receive(protocol: str, host: str, port: int, security: str, user: str, password: str) -> MailSession:
    cls = Pop3Session if protocol == "pop3" else ImapSession
    return cls(host, port, security, user, password)


def smtp_connect(host: str, port: int, security: str, user: str, password: str) -> smtplib.SMTP:
    try:
        if security == "ssl":
            s = smtplib.SMTP_SSL(host, port, timeout=TIMEOUT, context=_ctx())
        else:
            s = smtplib.SMTP(host, port, timeout=TIMEOUT)
            s.ehlo()
            if security == "starttls":
                s.starttls(context=_ctx())
                s.ehlo()
        s.login(user, password)
        return s
    except smtplib.SMTPAuthenticationError as e:
        raise MailError(f"SMTP sign-in failed. Check the password or app password. ({_clean(e)})") from None
    except (OSError, smtplib.SMTPException, ssl.SSLError) as e:
        raise MailError(f"Cannot use the SMTP server {host}:{port} ({_clean(e)}).") from None


def send_message(host: str, port: int, security: str, user: str, password: str,
                 msg: EmailMessage, rcpts: List[str]) -> None:
    s = smtp_connect(host, port, security, user, password)
    try:
        s.send_message(msg, to_addrs=rcpts)
    except smtplib.SMTPException as e:
        raise MailError(f"The server refused the message: {_clean(e)}") from None
    finally:
        try:
            s.quit()
        except Exception:
            pass


def _clean(e: Exception) -> str:
    s = e.args[0] if e.args else str(e)
    if isinstance(s, bytes):
        s = s.decode("utf-8", "replace")
    if isinstance(s, tuple):
        s = " ".join(x.decode("utf-8", "replace") if isinstance(x, bytes) else str(x) for x in s)
    return str(s)[:300]
