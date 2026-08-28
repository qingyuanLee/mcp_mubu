"""Mubu MCP — document ↔ Markdown / OPML / FreeMind conversion.

Ported from mubu-integration (liuboacean/mubu-integration) and adapted
for the MCP server context.
"""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from typing import Any, Dict, List


# ---------------------------------------------------------------------------
# Markdown export
# ---------------------------------------------------------------------------


def doc_to_markdown(node: Dict[str, Any], level: int = 0) -> str:
    """Recursively render a node subtree as a Markdown list fragment."""
    lines: List[str] = []
    text = (node.get("text") or "").replace("\n", " ")
    indent = " " * (2 * level)

    if node.get("checked") is not None or node.get("finish") is not None:
        mark = "x" if (node.get("checked") or node.get("finish")) else " "
        lines.append(f"{indent}- [{mark}] {text}")
    else:
        lines.append(f"{indent}- {text}")

    for child in node.get("children") or []:
        lines.append(doc_to_markdown(child, level + 1))

    note = node.get("note")
    if note:
        lines.append(f"{indent}> {note}")

    return "\n".join(lines)


def export_markdown(doc: Dict[str, Any]) -> str:
    """Convert a Mubu document structure to Markdown text.

    Handles both ``{"nodes": [...]}`` (API shape) and
    ``{"node": {...}}`` (round-trip shape).
    """
    nodes = doc.get("nodes")
    if nodes:
        lines: List[str] = []
        for node in nodes:
            title = (node.get("text") or "").replace("\n", " ")
            lines.append(f"# {title}")
            for child in node.get("children") or []:
                lines.append(doc_to_markdown(child, level=0))
            note = node.get("note")
            if note:
                lines.append(f"> {note}")
        return "\n".join(lines)

    root = doc.get("node") or doc
    if not isinstance(root, dict) or (not root.get("text") and not root.get("children")):
        raise ValueError("Invalid document structure")
    title = (root.get("text") or "").replace("\n", " ")
    lines = [f"# {title}"]
    for child in root.get("children") or []:
        lines.append(doc_to_markdown(child, level=0))
    note = root.get("note")
    if note:
        lines.append(f"> {note}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Markdown import
# ---------------------------------------------------------------------------


def markdown_to_doc(md: str) -> Dict[str, Any]:
    """Parse Markdown text into a Mubu document structure.

    Returns ``{"node": {"id": "root", "text": ..., "children": [...]}}``.
    """
    root_node: Dict[str, Any] = {"id": "root", "text": "", "children": []}
    counter = [0]

    def next_id() -> str:
        counter[0] += 1
        return f"node_{counter[0]}"

    lines = md.split("\n")
    headings: List[str] = []
    for line in lines:
        if not line.strip():
            continue
        m = re.match(r"^#+\s+(.*)$", line)
        if m:
            headings.append(m.group(1).strip())

    has_list = any(re.match(r"^\s*-\s+", line) for line in lines if line.strip())

    if not headings and not has_list:
        text = md.strip()
        if text:
            root_node["text"] = text
        return {"node": root_node}

    if headings:
        root_node["text"] = headings[0]
        for h in headings[1:]:
            root_node["children"].append({"id": next_id(), "text": h, "children": []})

    if not has_list:
        return {"node": root_node}

    stack: List[Any] = [(0, root_node)]

    for line in lines:
        if not line.strip():
            continue
        if re.match(r"^#+\s+", line):
            continue

        m_note = re.match(r"^(\s*)>\s+(.*)$", line)
        if m_note:
            note_depth = len(m_note.group(1)) // 2
            note_text = m_note.group(2).strip()
            target = root_node
            for d, n in reversed(stack):
                if d == note_depth:
                    target = n
                    break
            target["note"] = note_text
            continue

        m_list = re.match(r"^(\s*)-\s+(.*)$", line)
        if m_list:
            indent = len(m_list.group(1))
            depth = indent // 2
            content = m_list.group(2).strip()

            checked: Any = None
            mc = re.match(r"^\[([ xX])\]\s+(.*)$", content)
            if mc:
                checked = mc.group(1).lower() == "x"
                content = mc.group(2).strip()

            node: Dict[str, Any] = {"id": next_id(), "text": content, "children": []}
            if checked is not None:
                node["checked"] = checked

            while stack and stack[-1][0] >= depth:
                stack.pop()
            parent = stack[-1][1] if stack else root_node
            parent.setdefault("children", []).append(node)
            stack.append((depth, node))

    return {"node": root_node}


# ---------------------------------------------------------------------------
# Node normalisation (for changeset payloads)
# ---------------------------------------------------------------------------


def normalize_node(node: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively fill missing contract fields on a node dict."""
    if not isinstance(node, dict):
        return node
    now = int(time.time() * 1000)
    node.setdefault("note", "")
    node.setdefault("collapsed", False)
    node.setdefault("finish", False)
    node.setdefault("priority", 0)
    node.setdefault("color", 0)
    node.setdefault("createTime", node.get("timestamp") or now)
    node.setdefault("modifyTime", node.get("timestamp") or now)
    node.setdefault("timestamp", now)
    for child in node.get("children") or []:
        normalize_node(child)
    return node


# ---------------------------------------------------------------------------
# OPML export
# ---------------------------------------------------------------------------


def doc_to_opml(doc: Dict[str, Any]) -> str:
    """Convert a Mubu document to OPML 2.0 XML."""

    def build(node: Dict[str, Any], parent: ET.Element) -> None:
        text = (node.get("text") or "").replace("\n", " ")
        outline = ET.SubElement(parent, "outline", text=text)
        note = node.get("note")
        if note:
            outline.set("_note", note)
        for child in node.get("children") or []:
            build(child, outline)

    opml = ET.Element("opml", version="2.0")
    head = ET.SubElement(opml, "head")
    nodes = doc.get("nodes")
    if nodes:
        title = (nodes[0].get("text") or doc.get("name") or "mubu-export").replace("\n", " ")
        ET.SubElement(head, "title").text = title
        body = ET.SubElement(opml, "body")
        for node in nodes:
            build(node, body)
    else:
        root = doc.get("node") or doc
        title = (root.get("text") or "mubu-export").replace("\n", " ")
        ET.SubElement(head, "title").text = title
        body = ET.SubElement(opml, "body")
        build(root, body)

    ET.indent(opml, space="  ")
    return ET.tostring(opml, encoding="utf-8", xml_declaration=True).decode("utf-8")


# ---------------------------------------------------------------------------
# FreeMind (Freeplane) export
# ---------------------------------------------------------------------------


def doc_to_freeplane(doc: Dict[str, Any]) -> str:
    """Convert a Mubu document to FreeMind XML."""

    def build(node: Dict[str, Any], parent: ET.Element) -> None:
        for child in node.get("children") or []:
            text = (child.get("text") or "").replace("\n", " ")
            node_el = ET.SubElement(parent, "node", text=text)
            note = child.get("note")
            if note:
                note_el = ET.SubElement(node_el, "richcontent", type="note")
                ET.SubElement(note_el, "html").text = note
            build(child, node_el)

    mindmap = ET.Element("map", version="1.0.1")
    nodes = doc.get("nodes")
    if nodes:
        title = (nodes[0].get("text") or doc.get("name") or "mubu-export").replace("\n", " ")
        root_node = ET.SubElement(mindmap, "node", text=title)
        build(nodes[0], root_node)
        for extra in nodes[1:]:
            text = (extra.get("text") or "mubu-export").replace("\n", " ")
            extra_el = ET.SubElement(root_node, "node", text=text)
            note = extra.get("note")
            if note:
                note_el = ET.SubElement(extra_el, "richcontent", type="note")
                ET.SubElement(note_el, "html").text = note
            build(extra, extra_el)
    else:
        root = doc.get("node") or doc
        title = (root.get("text") or "mubu-export").replace("\n", " ")
        root_node = ET.SubElement(mindmap, "node", text=title)
        build(root, root_node)

    ET.indent(mindmap, space="  ")
    return ET.tostring(mindmap, encoding="utf-8", xml_declaration=True).decode("utf-8")


# ---------------------------------------------------------------------------
# Filename safety
# ---------------------------------------------------------------------------

_BAD_CHARS = ['/', ':', '*', '?', '"', '<', '>', '|', '\\']


def safe_filename(name: str) -> str:
    """Sanitise a name for use as a file name."""
    cleaned = ''.join('_' if ch in _BAD_CHARS else ch for ch in name).strip()
    return cleaned or 'untitled'
