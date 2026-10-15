"""XFDF annotation storage and OnlyOffice comment sync.

Line-for-line port of the helper functions in documents/views.py. Annotations
are stored exactly where Django kept them so existing data keeps working:

    MEDIA_ROOT/annotations/annotations_<version_id>_<user_id>.xfdf
    MEDIA_ROOT/annotations/onlyoffice_comments_<version_id>.json
    MEDIA_ROOT/annotated_pdfs/annotated_pdf_<user_id>_<version_id>.pdf
"""
import datetime
import json
import logging
import os
import uuid
import xml.etree.ElementTree as ET

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import is_manager_like
from app.config import settings
from app.models import AnnotationActivity, AssignedReviewer, DocumentVersion, User, utcnow
from app.services.viewer_common import get_full_name

log = logging.getLogger("turadome.viewer")

EMPTY_XFDF_WITH_ANNOTS = ('<?xml version="1.0" encoding="UTF-8"?><xfdf xmlns="http://ns.adobe.com/xfdf/" '
                          'xml:space="preserve"><annots></annots></xfdf>')
EMPTY_XFDF = ('<?xml version="1.0" encoding="UTF-8"?><xfdf xmlns="http://ns.adobe.com/xfdf/" '
              'xml:space="preserve"></xfdf>')


def annotations_dir() -> str:
    return os.path.join(str(settings.media_root), "annotations")


def xfdf_path(version_id: int, user_id: int) -> str:
    return os.path.join(annotations_dir(), f"annotations_{version_id}_{user_id}.xfdf")


def comments_path(version_id: int) -> str:
    return os.path.join(annotations_dir(), f"onlyoffice_comments_{version_id}.json")


def annotated_pdfs_dir() -> str:
    return os.path.join(str(settings.media_root), "annotated_pdfs")


def version_xfdf_files(version_id: int) -> list[str]:
    directory = annotations_dir()
    files = []
    if os.path.exists(directory):
        for filename in os.listdir(directory):
            if filename.startswith(f"annotations_{version_id}_") and filename.endswith(".xfdf"):
                files.append(os.path.join(directory, filename))
    return files


# ------------------------------------------------------------------ get_annotations_xfdf
def build_xfdf_for_user(db: Session, version: DocumentVersion, user: User) -> str:
    """Body of documents.views.get_annotations_xfdf (after its permission check)."""
    try:
        if user.user_type in ["admin", "manager", "teacher", "reviewer"] or is_manager_like(user) or user.is_superuser:
            # Privileged users always get ALL annotations merged (and no reviewer sticky notes)
            all_files = version_xfdf_files(version.id)
            if all_files:
                return merge_multiple_xfdf_files(db, all_files)

        own_path = xfdf_path(version.id, user.id)
        all_files = version_xfdf_files(version.id)

        if len(all_files) > 1 or (len(all_files) == 1 and not os.path.exists(own_path)):
            xfdf_content = merge_multiple_xfdf_files(db, all_files)
        elif os.path.exists(own_path):
            with open(own_path, "r", encoding="utf-8") as f:
                xfdf_content = f.read()
        else:
            xfdf_content = EMPTY_XFDF_WITH_ANNOTS

        # Add reviewer remarks as sticky note annotations
        try:
            root = ET.fromstring(xfdf_content)
            ns = {"xfdf": "http://ns.adobe.com/xfdf/"}
            annots = root.find(".//xfdf:annots", ns)
            if annots is None:
                annots = root.find(".//annots")
                if annots is None:
                    annots = ET.SubElement(root, "annots")

            reviews = db.execute(
                select(AssignedReviewer).where(
                    AssignedReviewer.document_version_id == version.id,
                    AssignedReviewer.remarks.is_not(None),
                    AssignedReviewer.remarks != "",
                )
            ).scalars().all()

            position_offset = 0
            for review in reviews:
                reviewer = review.user
                user_type = getattr(reviewer, "user_type", None)
                if reviewer.is_superuser:
                    color, role_text = "#FF0000", "Admin"
                elif user_type == "manager" or reviewer.is_manager:
                    color, role_text = "#0000FF", "Manager"
                elif user_type == "teacher":
                    color, role_text = "#00AA00", "Teacher"
                elif user_type == "reviewer":
                    color, role_text = "#FF8800", "Reviewer"
                else:
                    color = "#666666"
                    role_text = user_type.title() if user_type else "User"

                text_annot = ET.SubElement(annots, "text")
                text_annot.set("page", "0")
                y_position = 750 - (position_offset * 30)
                text_annot.set("rect", f"50,{y_position},70,{y_position + 20}")
                text_annot.set("color", color)
                text_annot.set("flags", "print,nozoom,norotate")
                text_annot.set("name", f"review_{review.id}_{uuid.uuid4().hex[:8]}")
                text_annot.set("title", f"{role_text}: {get_full_name(reviewer) or reviewer.username}")
                text_annot.set("subject", f"{role_text} Comment")
                text_annot.set("date", review.updated_at.strftime("%Y%m%d%H%M%S"))
                position_offset += 1
                contents = ET.SubElement(text_annot, "contents")
                contents.text = review.remarks

            xfdf_content = ET.tostring(root, encoding="unicode")
        except Exception as exc:  # noqa: BLE001 — Django returned the unmodified XFDF on error
            log.warning("Error adding reviewer remarks to XFDF: %s", exc)

        return xfdf_content
    except Exception:  # noqa: BLE001
        return EMPTY_XFDF


# ------------------------------------------------------------------ save_annotations_xfdf
def save_user_xfdf(db: Session, version: DocumentVersion, user: User, xfdf_data: str) -> str:
    """Write the user's XFDF file and log an AnnotationActivity (30-second dedup), as Django did."""
    filename = f"annotations_{version.id}_{user.id}.xfdf"
    path = os.path.join(annotations_dir(), filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(xfdf_data if xfdf_data else EMPTY_XFDF)

    annotation_count = xfdf_data.count("<annot") if xfdf_data else 0
    try:
        action = "modified" if annotation_count > 0 else "deleted"
        if annotation_count > 0:
            description = f"{annotation_count} annotation{'s' if annotation_count > 1 else ''}"
        else:
            description = "Annotations cleared"

        recent_threshold = utcnow() - datetime.timedelta(seconds=30)
        recent = db.execute(
            select(AnnotationActivity).where(
                AnnotationActivity.document_version_id == version.id,
                AnnotationActivity.user_id == user.id,
                AnnotationActivity.action == action,
                AnnotationActivity.created_at >= recent_threshold,
            ).order_by(AnnotationActivity.created_at.desc()).limit(1)
        ).scalar_one_or_none()

        if recent is not None:
            # keep the original timestamp; only refresh the description
            if recent.description != description:
                recent.description = description
                db.commit()
        else:
            db.add(AnnotationActivity(
                document_version_id=version.id,
                user_id=user.id,
                action=action,
                annotation_count=annotation_count,
                description=description,
            ))
            db.commit()
    except Exception as exc:  # noqa: BLE001 — activity logging never fails the save
        db.rollback()
        log.error("Error logging annotation activity: %s", exc)
    return filename


# ------------------------------------------------------------------ comment sync
def sync_onlyoffice_to_xfdf(version_id: int, comments_data: list, user_id: int) -> None:
    try:
        path = xfdf_path(version_id, user_id)
        existing_xfdf = ""
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                existing_xfdf = f.read()
        comment_annotations = convert_onlyoffice_comments_to_xfdf(comments_data)
        merged = merge_xfdf_with_onlyoffice_comments(existing_xfdf, comment_annotations)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(merged)
    except Exception as exc:  # noqa: BLE001
        log.error("Error syncing OnlyOffice to XFDF: %s", exc)


def convert_onlyoffice_comments_to_xfdf(comments_data: list) -> list[str]:
    xfdf_annotations = []
    for i, comment in enumerate(comments_data):
        annotation_xml = f'''<text page="{comment.get('page', 0)}"
                rect="{comment.get('x', 100)},{comment.get('y', 100)},{comment.get('x', 100) + 20},{comment.get('y', 100) + 20}"
                color="#FFA500"
                flags="print,nozoom,norotate"
                name="onlyoffice_comment_{i}"
                title="{comment.get('author', 'OnlyOffice User')}"
                subject="OnlyOffice Comment"
                date="{comment.get('date', '')}"
                creationdate="{comment.get('date', '')}"
                icon="Comment"
                state="Unmarked"
                statemodel="Review">
            <contents>{comment.get('text', '')}</contents>
        </text>'''
        xfdf_annotations.append(annotation_xml.strip())
    return xfdf_annotations


def merge_xfdf_with_onlyoffice_comments(existing_xfdf: str, comment_annotations: list[str]) -> str:
    try:
        if existing_xfdf.strip():
            try:
                root = ET.fromstring(existing_xfdf)
            except ET.ParseError:
                root = ET.fromstring(EMPTY_XFDF_WITH_ANNOTS)
        else:
            root = ET.fromstring(EMPTY_XFDF_WITH_ANNOTS)

        annots = root.find(".//{http://ns.adobe.com/xfdf/}annots")
        if annots is None:
            annots = ET.SubElement(root, "annots")

        to_remove = [a for a in list(annots) if a.get("name", "").startswith("onlyoffice_comment_")]
        for annotation in to_remove:
            annots.remove(annotation)

        for comment_xml in comment_annotations:
            try:
                annots.append(ET.fromstring(comment_xml))
            except ET.ParseError as exc:
                log.warning("Failed to parse comment XML: %s", exc)

        return ET.tostring(root, encoding="unicode", method="xml")
    except Exception as exc:  # noqa: BLE001
        log.error("Error merging XFDF: %s", exc)
        comment_xml = "\n".join(comment_annotations)
        return f'''<?xml version="1.0" encoding="UTF-8"?>
<xfdf xmlns="http://ns.adobe.com/xfdf/" xml:space="preserve">
    <annots>
        {comment_xml}
    </annots>
</xfdf>'''


def merge_multiple_xfdf_files(db: Session, xfdf_file_paths: list[str]) -> str:
    try:
        root = ET.Element("xfdf", xmlns="http://ns.adobe.com/xfdf/")
        root.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        annots = ET.SubElement(root, "annots")

        for file_path in xfdf_file_paths:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                file_tree = ET.fromstring(content)
                file_annots = file_tree.find(".//xfdf:annots", {"xfdf": "http://ns.adobe.com/xfdf/"})
                if file_annots is None:
                    file_annots = file_tree.find(".//annots")

                if file_annots is not None:
                    filename = os.path.basename(file_path)
                    parts = filename.split("_")
                    user_id = ""
                    if len(parts) >= 3:
                        user_id = parts[2].replace(".xfdf", "")
                        try:
                            owner = db.get(User, int(user_id))
                            if owner is None:
                                raise LookupError
                            user_name = get_full_name(owner) or owner.username
                        except Exception:  # noqa: BLE001 — Django: bare except
                            user_name = f"User {user_id}"
                    else:
                        user_name = "Unknown User"

                    for annotation in file_annots:
                        new_annotation = ET.fromstring(ET.tostring(annotation, encoding="unicode"))
                        current_title = new_annotation.get("title", "")
                        if current_title and user_name:
                            base_title = current_title.split(" - ")[0].strip()
                            user_name_clean = user_name.strip()
                            if base_title != user_name_clean and user_name_clean not in current_title and base_title:
                                new_annotation.set("title", f"{base_title} - {user_name_clean}")
                            else:
                                new_annotation.set("title", base_title if base_title else user_name_clean)
                        elif user_name:
                            new_annotation.set("title", user_name.strip())

                        if "onlyoffice_comment_" in new_annotation.get("name", ""):
                            color_map = {"1": "#FF6B6B", "2": "#4ECDC4", "3": "#45B7D1", "4": "#96CEB4"}
                            new_annotation.set("color", color_map.get(user_id, "#FFA500"))

                        annots.append(new_annotation)
            except Exception as exc:  # noqa: BLE001
                log.warning("Error processing %s: %s", file_path, exc)
                continue

        return ET.tostring(root, encoding="unicode", method="xml")
    except Exception as exc:  # noqa: BLE001
        log.error("Error merging XFDF files: %s", exc)
        return EMPTY_XFDF_WITH_ANNOTS


def convert_xfdf_to_onlyoffice_comments(xfdf_content: str) -> list[dict]:
    try:
        if not xfdf_content.strip():
            return []
        root = ET.fromstring(xfdf_content)
        comments = []
        found = (root.findall(".//{http://ns.adobe.com/xfdf/}square")
                 + root.findall(".//{http://ns.adobe.com/xfdf/}text")
                 + root.findall(".//{http://ns.adobe.com/xfdf/}freetext"))
        for annotation in found:
            if annotation.get("name", "").startswith("onlyoffice_comment_"):
                continue
            contents = annotation.find(".//{http://ns.adobe.com/xfdf/}contents")
            rect = annotation.get("rect", "100,100,120,120").split(",")
            comments.append({
                "id": annotation.get("name", f"pdftron_{len(comments)}"),
                "text": contents.text if contents is not None and contents.text else "",
                "author": annotation.get("title", "PDFTron User"),
                "date": annotation.get("date", ""),
                "page": int(annotation.get("page", 0)),
                "x": float(rect[0]) if len(rect) > 0 else 100,
                "y": float(rect[1]) if len(rect) > 1 else 100,
                "source": "pdftron",
            })
        return comments
    except Exception as exc:  # noqa: BLE001
        log.error("Error converting XFDF to OnlyOffice comments: %s", exc)
        return []


def debug_comment_sync_info(version_id: int, user_id: int) -> dict:
    """documents.views.debug_comment_sync"""
    info: dict = {}
    c_path = comments_path(version_id)
    if os.path.exists(c_path):
        with open(c_path, "r", encoding="utf-8") as f:
            oo_comments = json.load(f)
        info["onlyoffice_comments"] = oo_comments
        info["onlyoffice_count"] = len(oo_comments)
    else:
        info["onlyoffice_comments"] = []
        info["onlyoffice_count"] = 0

    x_path = xfdf_path(version_id, user_id)
    if os.path.exists(x_path):
        with open(x_path, "r", encoding="utf-8") as f:
            xfdf_content = f.read()
        info["xfdf_content"] = xfdf_content
        info["xfdf_length"] = len(xfdf_content)
        try:
            root = ET.fromstring(xfdf_content)
            anns = (root.findall(".//{http://ns.adobe.com/xfdf/}text")
                    + root.findall(".//{http://ns.adobe.com/xfdf/}square")
                    + root.findall(".//{http://ns.adobe.com/xfdf/}freetext"))
            info["xfdf_annotation_count"] = len(anns)
            info["xfdf_annotations"] = []
            for ann in anns:
                contents = ann.find(".//{http://ns.adobe.com/xfdf/}contents")
                info["xfdf_annotations"].append({
                    "name": ann.get("name", "unnamed"),
                    "title": ann.get("title", ""),
                    "subject": ann.get("subject", ""),
                    "contents": contents.text if contents is not None else None,
                })
        except Exception as exc:  # noqa: BLE001
            info["xfdf_parse_error"] = str(exc)
    else:
        info["xfdf_content"] = None
        info["xfdf_length"] = 0
        info["xfdf_annotation_count"] = 0

    info["file_paths"] = {
        "onlyoffice_comments_path": c_path,
        "xfdf_path": x_path,
        "onlyoffice_exists": os.path.exists(c_path),
        "xfdf_exists": os.path.exists(x_path),
    }
    return info


def convert_annotations_to_xfdf(annotations) -> str:
    """documents.views.convert_annotations_to_xfdf (unused by the UI; kept for parity)."""
    header = '''<?xml version="1.0" encoding="UTF-8"?>
<xfdf xmlns="http://ns.adobe.com/xfdf/" xml:space="preserve">
    <annots>'''
    footer = '''    </annots>
</xfdf>'''
    parts = []
    for a in annotations:
        x, y, w, h = float(a.x_position), float(a.y_position), float(a.width), float(a.height)
        title = get_full_name(a.user)
        date = a.created_at.replace(tzinfo=datetime.timezone.utc).isoformat()
        if a.annotation_type == "highlight":
            parts.append(f'''
        <highlight page="{a.page_number - 1}" rect="{x},{y},{x + w},{y + h}" color="{a.color}" opacity="0.5" title="{title}" subject="Highlight" date="{date}">
            <contents>{a.content}</contents>
        </highlight>''')
        else:
            parts.append(f'''
        <text page="{a.page_number - 1}" rect="{x},{y},{x + 20},{y + 20}" color="{a.color}" title="{title}" subject="{a.annotation_type.title()}" date="{date}" icon="Comment">
            <contents>{a.content}</contents>
        </text>''')
    if not parts:
        return header + footer
    return header + "".join(parts) + footer
