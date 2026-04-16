#!/usr/bin/env python3
"""Confluence XHTML → Plane TipTap HTML converter (v2: proper XML parser).

Replaces the regex-based convert_final.py with lxml-based parsing.

Plane editor supported HTML:
  Nodes: p.editor-paragraph-block, h1-h6.editor-heading-block,
         ul, ol, li, pre>code, blockquote, table/tr/th/td (colwidth),
         image-component, div[data-type=horizontalRule]
  Marks: strong/b, em/i, u, s/del, code, a[href] (full URL, no relative),
         span[data-text-color] (NO style attr), span[data-background-color]
"""
import sys, json, re
from lxml import etree

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

P = "editor-paragraph-block"
H = "editor-heading-block"
EDITOR_WIDTH = 720

# Load mappings
with open('jira_migrate_scripts/data/page_asset_map.json') as f:
    asset_map = json.load(f)
with open('jira_migrate_scripts/data/page_map.json') as f:
    page_map = json.load(f)
with open('jira_migrate_scripts/data/title_to_plane_id.json', encoding='utf-8') as f:
    title_to_plane = json.load(f)
with open('jira_migrate_scripts/data/title_stripped_to_plane_id.json', encoding='utf-8') as f:
    title_stripped_to_plane = json.load(f)
with open('jira_migrate_scripts/data/page_to_project.json') as f:
    page_to_project = json.load(f)


def _text(el):
    """Get all text content of an element."""
    return ''.join(el.itertext()).strip()


def _strip_ns(tag):
    """Remove namespace from tag name."""
    if '}' in tag:
        return tag.split('}', 1)[1]
    return tag


def _convert_element(el):
    """Convert a single Confluence XHTML element to Plane HTML."""
    tag = _strip_ns(el.tag)

    # --- Confluence structured macros ---
    if tag == 'structured-macro':
        name = el.get('{http://atlassian.com/content}name', el.get('ac:name', ''))
        return _convert_macro(el, name)

    # --- Confluence links ---
    if tag == 'link':
        return _convert_link(el)

    # --- Confluence images ---
    if tag == 'image':
        return _convert_image(el)

    # --- Confluence inline-comment-marker ---
    if tag == 'inline-comment-marker':
        return _children_html(el)

    # --- Confluence layout (flatten) ---
    if tag in ('layout', 'layout-section', 'layout-cell'):
        return _children_html(el)

    # --- Confluence emoticons ---
    if tag == 'emoticon':
        return ''

    # --- Standard HTML elements ---
    if tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
        inner = _children_html(el)
        return f'<{tag} class="{H}">{inner}</{tag}>'

    if tag == 'p':
        inner = _children_html(el)
        return f'<p class="{P}">{inner}</p>'

    if tag == 'hr':
        return '<div class="py-4 border-strong-1" data-type="horizontalRule"><div></div></div>'

    if tag == 'br':
        return '<br />'

    if tag == 'table':
        return _convert_table(el)

    if tag in ('tr', 'tbody', 'thead'):
        inner = _children_html(el)
        return f'<{tag}>{inner}</{tag}>'

    if tag in ('th', 'td'):
        attrs = ''
        colspan = el.get('colspan')
        rowspan = el.get('rowspan')
        colwidth = el.get('colwidth')
        if colspan:
            attrs += f' colspan="{colspan}"'
        if rowspan:
            attrs += f' rowspan="{rowspan}"'
        if colwidth:
            attrs += f' colwidth="{colwidth}"'
        inner = _children_html(el)
        return f'<{tag}{attrs}>{inner}</{tag}>'

    if tag in ('ul', 'ol', 'li', 'blockquote'):
        inner = _children_html(el)
        return f'<{tag}>{inner}</{tag}>'

    if tag == 'pre':
        inner = _children_html(el)
        # If pre contains rich content (links, spans, etc.), convert to paragraph
        # TipTap's code block only supports plain text
        if '<a ' in inner or 'data-text-color' in inner or '<strong' in inner or '<em' in inner:
            return f'<p class="{P}">{inner}</p>'
        return f'<pre>{inner}</pre>'

    if tag == 'code':
        lang = el.get('class', '')
        lang_attr = ''
        if lang and lang.startswith('language-'):
            lang_attr = f' class="{lang}"'
        inner = _children_html(el)
        return f'<code{lang_attr}>{inner}</code>'

    if tag == 'a':
        href = el.get('href', '')
        text = _children_html(el) or href
        if href:
            return f'<a href="{href}" target="_blank" rel="noopener noreferrer nofollow">{text}</a>'
        return text

    if tag == 'img':
        src = el.get('src', '')
        if src:
            return f'<img src="{src}" />'
        return ''

    if tag == 'span':
        return _convert_span(el)

    if tag in ('strong', 'b'):
        inner = _children_html(el)
        return f'<strong>{inner}</strong>'

    if tag in ('em', 'i'):
        inner = _children_html(el)
        return f'<em>{inner}</em>'

    if tag == 'u':
        inner = _children_html(el)
        return f'<u>{inner}</u>'

    if tag in ('s', 'del', 'strike'):
        inner = _children_html(el)
        return f'<s>{inner}</s>'

    if tag == 'sub':
        inner = _children_html(el)
        return f'<sub>{inner}</sub>'

    if tag == 'sup':
        inner = _children_html(el)
        return f'<sup>{inner}</sup>'

    # --- Confluence-specific tags to strip (keep content) ---
    if tag in ('rich-text-body', 'link-body', 'plain-text-link-body',
               'plain-text-body', 'parameter', 'page', 'attachment',
               'url', 'user', 'space', 'default-parameter'):
        return _children_html(el)

    # --- Unknown tags: keep content, drop tag ---
    return _children_html(el)


def _children_html(el):
    """Get HTML for all children of an element, including text/tail."""
    parts = []
    if el.text:
        parts.append(_escape(el.text))
    for child in el:
        parts.append(_convert_element(child))
        if child.tail:
            parts.append(_escape(child.tail))
    return ''.join(parts)


def _escape(text):
    """Escape HTML special characters."""
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _convert_span(el):
    """Convert span, extracting color from style to data attributes."""
    style = el.get('style', '')
    inner = _children_html(el)

    attrs = ''
    # Extract text color
    color_m = re.search(r'(?<!background-)color:\s*([^;"]+)', style)
    if color_m:
        color = color_m.group(1).strip()
        attrs += f' data-text-color="{color}"'

    # Extract background color
    bg_m = re.search(r'background-color:\s*([^;"]+)', style)
    if bg_m:
        bg = bg_m.group(1).strip()
        attrs += f' data-background-color="{bg}"'

    if attrs:
        return f'<span{attrs}>{inner}</span>'
    return f'<span>{inner}</span>'


def _convert_macro(el, name):
    """Convert ac:structured-macro."""
    if name == 'code':
        # Code block
        lang = ''
        for param in el.iter():
            if _strip_ns(param.tag) == 'parameter' and param.get('{http://atlassian.com/content}name', param.get('ac:name', '')) == 'language':
                lang = _text(param)
        body = ''
        for child in el.iter():
            if _strip_ns(child.tag) == 'plain-text-body':
                # Get CDATA content
                body = child.text or ''
                if body.startswith('<![CDATA['):
                    body = body[9:]
                if body.endswith(']]>'):
                    body = body[:-3]
                break
        lang_attr = f' class="language-{lang}"' if lang else ''
        return f'<pre><code{lang_attr}>{_escape(body)}</code></pre>'

    # For other macros (expand, panel, info, note, warning, etc.): extract content
    # Try rich-text-body first, then plain-text-body as paragraph (NOT code block)
    for child in el.iter():
        t = _strip_ns(child.tag)
        if t == 'rich-text-body':
            return _children_html(child)
        if t == 'plain-text-body':
            body = child.text or ''
            if body.startswith('<![CDATA['):
                body = body[9:]
            if body.endswith(']]>'):
                body = body[:-3]
            body = body.strip()
            if body:
                return f'<p class="{P}">{_escape(body)}</p>'
            return ''

    return ''


def _convert_link(el):
    """Convert ac:link."""
    # Find target
    url = None
    page_title = None
    link_text = None

    for child in el.iter():
        t = _strip_ns(child.tag)
        if t == 'url':
            url = child.get('{http://atlassian.com/resource/identifier}value',
                           child.get('ri:value', ''))
        if t == 'page':
            page_title = child.get('{http://atlassian.com/resource/identifier}content-title',
                                   child.get('ri:content-title', ''))
        if t == 'plain-text-link-body':
            body = child.text or ''
            if '<![CDATA[' in body:
                body = body.replace('<![CDATA[', '').replace(']]>', '')
            link_text = body.strip()
        if t == 'link-body':
            link_text = _children_html(child)

    if url:
        text = link_text or url
        return f'<a href="{url}" target="_blank" rel="noopener noreferrer nofollow">{text}</a>'

    if page_title:
        text = link_text or page_title
        # Resolve to Plane page URL
        plane_id = title_to_plane.get(page_title)
        if not plane_id:
            stripped = re.sub(r'<[^>]+>', '', page_title).strip()
            plane_id = title_stripped_to_plane.get(stripped)
        if plane_id:
            project_id = page_to_project.get(plane_id)
            clean_text = re.sub(r'<[^>]+>', '', text).strip() or page_title
            if project_id:
                return f'<a href="https://plane.example.com/keis/projects/{project_id}/pages/{plane_id}/">{clean_text}</a>'
        return f'[Page: {text}]'

    return link_text or ''


def _convert_image(el):
    """Convert ac:image."""
    for child in el.iter():
        t = _strip_ns(child.tag)
        if t == 'attachment':
            filename = child.get('{http://atlassian.com/resource/identifier}filename',
                                child.get('ri:filename', ''))
            aid = asset_map.get(filename)
            if aid:
                return f'<image-component id="{aid}" src="{aid}" data-id="{aid}" status="uploaded"></image-component>'
            return ''
        if t == 'url':
            src = child.get('{http://atlassian.com/resource/identifier}value',
                           child.get('ri:value', ''))
            if src:
                return f'<img src="{src}" />'
    return ''


def _convert_table(el):
    """Convert table. Set colwidth = editor_width / num_cols to fill the editor width."""
    inner = _children_html(el)

    # Count columns from first row
    first_row = re.search(r'<tr[^>]*>(.*?)</tr>', inner, re.DOTALL)
    if first_row:
        num_cols = len(re.findall(r'<t[hd]', first_row.group(1)))
        if num_cols > 0:
            col_w = max(50, EDITOR_WIDTH // num_cols)
            def add_cw(m):
                if 'colwidth' in m.group(0):
                    return m.group(0)
                return m.group(0)[:-1] + f' colwidth="{col_w}">'
            inner = re.sub(r'<(t[hd])([^>]*)>', add_cw, inner)

    return f'<table>{inner}</table>'


def _clean_html(html):
    """Post-process: remove empty paragraphs, normalize whitespace."""
    # Remove empty paragraphs
    html = re.sub(rf'<p class="{P}"><br\s*/?></p>', '', html)
    html = re.sub(rf'<p class="{P}"></p>', '', html)
    return html.strip()


def _replace_html_entities(xhtml):
    """Replace HTML named entities with numeric references (XML only knows &amp; &lt; &gt; &quot; &apos;)."""
    import html.entities
    def _repl(m):
        name = m.group(1)
        if name in ('amp', 'lt', 'gt', 'quot', 'apos'):
            return m.group(0)  # keep XML-native entities
        cp = html.entities.name2codepoint.get(name)
        if cp:
            return f'&#{cp};'
        return m.group(0)  # unknown entity, keep as-is
    return re.sub(r'&([a-zA-Z]+);', _repl, xhtml)


def confluence_to_tiptap(xhtml):
    """Convert Confluence XHTML to Plane TipTap HTML."""
    # Replace HTML entities with numeric references for XML parser
    xhtml = _replace_html_entities(xhtml)

    # Wrap in root element for parsing
    wrapped = f'<root xmlns:ac="http://atlassian.com/content" xmlns:ri="http://atlassian.com/resource/identifier">{xhtml}</root>'

    try:
        root = etree.fromstring(wrapped.encode('utf-8'))
    except etree.XMLSyntaxError:
        # Fallback: try to fix common issues
        try:
            parser = etree.XMLParser(recover=True)
            root = etree.fromstring(wrapped.encode('utf-8'), parser)
        except Exception:
            # Last resort: return escaped text
            return f'<p class="{P}">{_escape(xhtml[:1000])}</p>'

    return _clean_html(_children_html(root))


# === Main ===
count = 0
with open('jira_migrate_scripts/data/page_final.jsonl', 'w', encoding='utf-8') as out:
    with open('jira_migrate_scripts/data/confluence_pages.jsonl', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('mysql:'):
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            cid = str(d['id'])
            plane_id = page_map.get(cid)
            if not plane_id or not d.get('body'):
                continue
            tiptap = confluence_to_tiptap(d['body'])
            out.write(json.dumps({'id': plane_id, 'html': tiptap}, ensure_ascii=False) + '\n')
            count += 1

# Verify
conf_pages = {}
with open('jira_migrate_scripts/data/confluence_pages.jsonl', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith('mysql:'):
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        conf_pages[str(d['id'])] = d

rev_map = {v: k for k, v in page_map.items()}
final_pages = {}
with open('jira_migrate_scripts/data/page_final.jsonl', encoding='utf-8') as f:
    for line in f:
        d = json.loads(line.strip())
        final_pages[d['id']] = d['html']

import html as html_mod

def _normalize_heading(text):
    """Normalize heading text for comparison (decode entities, normalize whitespace)."""
    # Decode HTML entities
    text = html_mod.unescape(text)
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text

pages_with_missing = 0
total_missing = 0
for pid, page_html in final_pages.items():
    cid = rev_map.get(pid)
    if not cid or cid not in conf_pages:
        continue
    conf_sections = [_normalize_heading(s) for s in re.findall(r'<h[1-6][^>]*>([^<]+)</h', conf_pages[cid]['body'])]
    db_sections = [_normalize_heading(s) for s in re.findall(r'<h[1-6][^>]*>([^<]+)</h', page_html)]
    missing = [s for s in conf_sections if s not in db_sections]
    if missing:
        pages_with_missing += 1
        total_missing += len(missing)

print(f'Pages: {count}')
print(f'Pages with missing sections: {pages_with_missing}')
print(f'Total missing sections: {total_missing}')
