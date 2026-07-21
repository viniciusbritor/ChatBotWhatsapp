"""Ata helper - generates meeting minutes from Calendar + Gmail data."""
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


async def generate_ata_markdown(
    event: Dict[str, Any],
    emails: List[Dict[str, Any]],
    additional_notes: Optional[str] = None,
) -> str:
    """Generate meeting minutes in markdown.

    Args:
        event: Calendar event dict
        emails: List of email messages from thread
        additional_notes: Optional extra context

    Returns:
        Markdown formatted ata
    """
    title = event.get("summary", "Reuniao")
    start = event.get("start", "")
    end = event.get("end", "")
    attendees = event.get("attendees", [])
    description = event.get("description", "")
    location = event.get("location", "")

    ata_parts = [
        f"# {title}",
        "",
        f"**Data:** {start} - {end}",
    ]
    if location:
        ata_parts.append(f"**Local:** {location}")
    if attendees:
        ata_parts.append(f"**Participantes:** {', '.join(attendees)}")
    if description:
        ata_parts.append(f"\n## Pauta\n{description}")

    ata_parts.append("\n## Discussao\n")
    if emails:
        for email in emails:
            ata_parts.append(f"### {email.get('from', 'unknown')}")
            ata_parts.append(f"_{email.get('date', '')}_\n")
            body = email.get("body", "")
            if body:
                ata_parts.append(body[:500])
            ata_parts.append("")

    if additional_notes:
        ata_parts.append(f"\n## Notas Adicionais\n{additional_notes}")

    ata_parts.append("\n## Decisoes\n")
    ata_parts.append("- _(a ser preenchido)_")

    ata_parts.append("\n## Proximos Passos\n")
    ata_parts.append("- _(a ser preenchido)_")

    return "\n".join(ata_parts)


async def save_ata_to_drive(
    phone: str,
    event: Dict[str, Any],
    ata_markdown: str,
) -> Dict[str, Any]:
    """Save ata markdown to Drive/Omnichannel/Atas/.

    Args:
        phone: User phone for per-user OAuth token (mandatory, Fase D).
        event: Calendar event
        ata_markdown: Markdown content

    Returns:
        {"file": {...}} or {"error": str}
    """
    from tools.google_drive import find_omnichannel_atas_folder, upload_file

    folder_result = await find_omnichannel_atas_folder(phone)
    if "error" in folder_result:
        return folder_result

    folder_id = folder_result["folder_id"]
    start = event.get("start", "")[:10]
    title_slug = event.get("summary", "reuniao").replace(" ", "_").replace("/", "-")[:50]
    filename = f"{start}_{title_slug}.md"

    return await upload_file(phone, folder_id, filename, ata_markdown, mime_type="text/markdown")


async def notify_organizer(
    phone: str,
    organizer_email: str,
    event_title: str,
    drive_link: str,
    ata_summary: str,
) -> Dict[str, Any]:
    """Notify organizer via email with link to ata.

    Args:
        phone: User phone for per-user OAuth token (mandatory, Fase D).
        organizer_email: Organizer email
        event_title: Meeting title
        drive_link: Link to ata file in Drive
        ata_summary: Brief summary text

    Returns:
        {"message": {...}} or {"error": str}
    """
    from tools.google_gmail import send_message

    subject = f"Ata: {event_title}"
    body = (
        f"Ola,\n\n"
        f"A ata da reuniao '{event_title}' foi gerada e salva no Drive.\n\n"
        f"Link: {drive_link}\n\n"
        f"Resumo:\n{ata_summary}\n\n"
        f"Qualquer ajuste, me avise.\n\n"
        f"Jennifer"
    )
    return await send_message(phone, organizer_email, subject, body)


def _now_iso():
    return datetime.now(timezone.utc).isoformat()
