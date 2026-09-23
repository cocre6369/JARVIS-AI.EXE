"""Email skills — DRAFT ONLY, inside the user's already-logged-in Outlook.

Hard rules enforced here (beyond the guardrails layer):
* never sends mail — drafts open on screen and the user presses Send;
* never touches accounts, logins or passwords;
* reading the selected message requires an explicit user confirmation
  (policy on the tool) because it surfaces private content to the model.
"""
from __future__ import annotations

import sys
from typing import Any, Dict, Optional
from urllib.parse import quote

from . import register
from ..guardrails import POLICY_CONFIRM


def _outlook():
    """Return an Outlook Application COM object, or None."""
    if sys.platform != "win32":
        return None
    try:
        import win32com.client  # type: ignore

        return win32com.client.Dispatch("Outlook.Application")
    except Exception:
        return None


def _selected_mail():
    app = _outlook()
    if app is None:
        return None, "Outlook is not available on this machine."
    try:
        explorer = app.ActiveExplorer()
        selection = explorer.Selection
        if selection.Count < 1:
            return None, ("No message is selected in Outlook — select the email "
                          "you mean in the inbox first, then ask me again.")
        item = selection.Item(1)
        # 0 = MailItem
        if getattr(item, "Class", 0) != 43:  # olMail
            return None, "The selected item is not an email message."
        return item, ""
    except Exception as exc:
        return None, f"Could not read the selected message ({exc})."


@register("email_read_selected", "Read the email currently SELECTED in Outlook "
          "(subject, sender, body preview) so you can draft a reply. "
          "Privacy-sensitive.", "{}", policy=POLICY_CONFIRM, returns_data=True)
def email_read_selected() -> str:
    item, err = _selected_mail()
    if item is None:
        return f"ERROR: {err}"
    try:
        body = str(getattr(item, "Body", "") or "")
        data: Dict[str, Any] = {
            "subject": str(getattr(item, "Subject", "") or ""),
            "from": str(getattr(item, "SenderName", "") or ""),
            "to": str(getattr(item, "To", "") or ""),
            "received": str(getattr(item, "ReceivedTime", "") or ""),
            "body": body[:2500],
        }
        return (f"SELECTED EMAIL — subject: {data['subject']!r}; "
                f"from: {data['from']!r}; body: {data['body']!r}")
    except Exception as exc:
        return f"ERROR: could not read the message ({exc})."


@register("email_reply_draft", "Create a REPLY draft (never sends) in Outlook "
          "for the currently selected email and display it for review.",
          "{body}", policy=POLICY_CONFIRM)
def email_reply_draft(body: str) -> str:
    item, err = _selected_mail()
    if item is None:
        return f"ERROR: {err}"
    try:
        draft = item.Reply()
        draft.Body = body
        draft.Display(False)   # show it — the Send button belongs to the user
        return ("Reply draft prepared and opened in Outlook for your review. "
                "I never send — the Send button is yours.")
    except Exception as exc:
        return f"ERROR: could not create the reply draft ({exc})."


@register("email_compose", "Open a new email draft (Outlook if present, "
          "otherwise the system mail client). Never sends.",
          "{to, subject, body}", policy=POLICY_CONFIRM)
def email_compose(body: str, subject: str = "", to: str = "") -> str:
    app = _outlook()
    if app is not None:
        try:
            draft = app.CreateItem(0)  # olMailItem
            if to:
                draft.To = to
            draft.Subject = subject or ""
            draft.Body = body or ""
            draft.Display(False)
            return ("Draft created and opened in Outlook for your review — "
                    "nothing is sent without you.")
        except Exception:
            pass
    url = f"mailto:{quote(to or '')}?subject={quote(subject or '')}&body={quote(body or '')}"
    import webbrowser

    webbrowser.open(url)
    return ("Opened your default mail client with the draft prefilled. "
            "Review it and send when ready.")
