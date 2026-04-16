#!/usr/bin/env python3
"""Final Confluence → TipTap conversion with nested macro fix."""
import sys, json, re
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

P = "editor-paragraph-block"
H = "editor-heading-block"

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


def confluence_to_tiptap(xhtml):
    h = xhtml

    # Images
    def replace_image(m):
        content = m.group(0)
        att_m = re.search(r'ri:attachment ri:filename="([^"]*)"', content)
        url_m = re.search(r'ri:url ri:value="([^"]*)"', content)
        if att_m:
            aid = asset_map.get(att_m.group(1))
            if aid:
                return f'<image-component id="{aid}" src="{aid}" data-id="{aid}" status="uploaded"></image-component>'
            return ''
        if url_m:
            return f'<img src="{url_m.group(1)}" />'
        return ''
    h = re.sub(r'<ac:image[^>]*>.*?</ac:image>', replace_image, h, flags=re.DOTALL)
    h = re.sub(r'<ac:image[^>]*/>', '', h)

    # Code blocks
    def replace_code(m):
        body = m.group(1)
        lang_m = re.search(r'ac:parameter ac:name="language">([^<]+)', body)
        lang = lang_m.group(1) if lang_m else ''
        body_m = re.search(r'<ac:plain-text-body>\s*<!\[CDATA\[(.*?)\]\]>\s*</ac:plain-text-body>', body, re.DOTALL)
        code = body_m.group(1) if body_m else ''
        la = f' class="language-{lang}"' if lang else ''
        return f'<pre><code{la}>{code}</code></pre>'
    h = re.sub(r'<ac:structured-macro ac:name="code"[^>]*>(.*?)</ac:structured-macro>', replace_code, h, flags=re.DOTALL)

    # ITERATIVE macro processing - innermost first
    for _ in range(10):
        def replace_innermost(m):
            content = m.group(1)
            rtb = re.search(r'<ac:rich-text-body>(.*)</ac:rich-text-body>', content, re.DOTALL)
            if rtb:
                return rtb.group(1)
            ptb = re.search(r'<ac:plain-text-body>\s*<!\[CDATA\[(.*?)\]\]>\s*</ac:plain-text-body>', content, re.DOTALL)
            if ptb:
                return f'<pre><code>{ptb.group(1)}</code></pre>'
            return ''
        new = re.sub(
            r'<ac:structured-macro ac:name="[^"]*"[^>]*>((?:(?!<ac:structured-macro).)*?)</ac:structured-macro>',
            replace_innermost, h, flags=re.DOTALL)
        if new == h:
            break
        h = new

    # Inline comment markers
    h = re.sub(r'<ac:inline-comment-marker[^>]*>(.*?)</ac:inline-comment-marker>', r'\1', h, flags=re.DOTALL)

    # Links
    def replace_link(m):
        content = m.group(1)
        url_m = re.search(r'ri:url ri:value="([^"]*)"', content)
        page_m = re.search(r'ri:page ri:content-title="([^"]*)"', content)
        body_m = re.search(r'<ac:plain-text-link-body>\s*<!\[CDATA\[(.*?)\]\]>\s*</ac:plain-text-link-body>', content, re.DOTALL)
        link_body_m = re.search(r'<ac:link-body>(.*?)</ac:link-body>', content, re.DOTALL)
        text = body_m.group(1) if body_m else (link_body_m.group(1) if link_body_m else None)
        if url_m:
            t = text or url_m.group(1)
            return f'<a href="{url_m.group(1)}" target="_blank" rel="noopener noreferrer nofollow">{t}</a>'
        if page_m:
            t = text or page_m.group(1)
            title_raw = page_m.group(1)
            # Try exact title match, then stripped-HTML match
            plane_id = title_to_plane.get(title_raw)
            if not plane_id:
                stripped = re.sub(r'<[^>]+>', '', title_raw).strip()
                plane_id = title_stripped_to_plane.get(stripped)
            if plane_id:
                project_id = page_to_project.get(plane_id)
                clean_text = re.sub(r'<[^>]+>', '', t).strip() or title_raw
                if project_id:
                    return f'<a href="https://plane.example.com/keis/projects/{project_id}/pages/{plane_id}/">{clean_text}</a>'
                return f'<a data-page-id="{plane_id}">{clean_text}</a>'
            return f'[Page: {t}]'
        return text or ''
    h = re.sub(r'<ac:link[^>]*>(.*?)</ac:link>', replace_link, h, flags=re.DOTALL)

    # Strip remaining Confluence tags
    h = re.sub(r'</?ac:[a-z-]+[^>]*>', '', h)
    h = re.sub(r'<ri:[a-z-]+[^>]*/>', '', h)
    h = re.sub(r'</?ri:[a-z-]+[^>]*>', '', h)
    h = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', h, flags=re.DOTALL)
    h = re.sub(r'<ac:emoticon[^>]*/>', '', h)

    # Table width: convert table style="width: X%" to colwidth on cells
    EDITOR_WIDTH = 720  # Plane editor max-width in px
    def fix_table_width(m):
        table_tag = m.group(1)
        table_body = m.group(2)
        width_m = re.search(r'width:\s*([\d.]+)%', table_tag)
        if not width_m:
            return m.group(0)
        table_px = int(float(width_m.group(1)) / 100 * EDITOR_WIDTH)
        # Count columns from first row
        first_row = re.search(r'<tr[^>]*>(.*?)</tr>', table_body, re.DOTALL)
        if not first_row:
            return m.group(0)
        num_cols = len(re.findall(r'<t[hd]', first_row.group(1)))
        if num_cols == 0:
            return m.group(0)
        col_w = max(50, table_px // num_cols)
        # Add colwidth to all th/td that don't already have it
        def add_colwidth(cell_m):
            tag = cell_m.group(0)
            if 'colwidth' in tag:
                return tag
            return tag[:-1] + f' colwidth="{col_w}">'
        new_body = re.sub(r'<(t[hd])([^>]*)>', add_colwidth, table_body)
        return f'<table>{new_body}</table>'
    h = re.sub(r'<table([^>]*)>(.*?)</table>', fix_table_width, h, flags=re.DOTALL)

    # TipTap format
    h = re.sub(r'<hr\s*/?>', '<div class="py-4 border-strong-1" data-type="horizontalRule"><div></div></div>', h)

    def fix_color_span(m):
        attrs = m.group(1)
        color_m = re.search(r'color:\s*([^;"]+)', attrs)
        bg_m = re.search(r'background-color:\s*([^;"]+)', attrs)
        r = ''
        if color_m:
            r += f' data-text-color="{color_m.group(1).strip()}" style="color: {color_m.group(1).strip()}"'
        if bg_m:
            r += f' data-background-color="{bg_m.group(1).strip()}" style="background-color: {bg_m.group(1).strip()}"'
        return f'<span{r or " " + attrs}>'
    h = re.sub(r'<span\s+style="([^"]*(?:color|background)[^"]*)">', fix_color_span, h)

    h = re.sub(r'<p class="[^"]*">', f'<p class="{P}">', h)
    h = re.sub(r'<p(?!\s[^>]*class)(\s[^>]*)?>',  f'<p class="{P}">', h)
    for lv in ['1', '2', '3', '4', '5', '6']:
        h = re.sub(f'<h{lv} class="[^"]*">', f'<h{lv} class="{H}">', h)
        h = re.sub(f'<h{lv}(?!\\s[^>]*class)(\\s[^>]*)?>',  f'<h{lv} class="{H}">', h)

    # Fix block nesting
    block_tags = r'(?:h[1-6]|div|table|ul|ol|pre|blockquote|image-component)'
    for _ in range(5):
        new = re.sub(
            rf'(<p[^>]*>)((?:(?!</p>).)*?)(<(?:{block_tags})[ >])',
            lambda m: m.group(1) + m.group(2) + '</p>' + m.group(3),
            h, flags=re.DOTALL)
        if new == h:
            break
        h = new
    h = re.sub(rf'(</(?:{block_tags})>)\s*</p>', r'\1', h)

    # Clean empty paragraphs
    h = re.sub(rf'<p class="{P}"><br\s*/?></p>', '', h)
    h = re.sub(rf'<p class="{P}"></p>', '', h)
    h = re.sub(r'>\s+<', '><', h)

    return h.strip()


# Process
count = 0
with open('jira_migrate_scripts/data/page_final.jsonl', 'w', encoding='utf-8') as out:
    with open('jira_migrate_scripts/data/confluence_pages.jsonl', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('mysql:'):
                continue
            try:
                d = json.loads(line)
            except:
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
        except:
            continue
        conf_pages[str(d['id'])] = d

rev_map = {v: k for k, v in page_map.items()}
final_pages = {}
with open('jira_migrate_scripts/data/page_final.jsonl', encoding='utf-8') as f:
    for line in f:
        d = json.loads(line.strip())
        final_pages[d['id']] = d['html']

pages_with_missing = 0
total_missing = 0
for pid, html in final_pages.items():
    cid = rev_map.get(pid)
    if not cid or cid not in conf_pages:
        continue
    conf_sections = re.findall(r'<h[1-6][^>]*>([^<]+)</h', conf_pages[cid]['body'])
    db_sections = re.findall(r'<h[1-6][^>]*>([^<]+)</h', html)
    missing = [s for s in conf_sections if s not in db_sections]
    if missing:
        pages_with_missing += 1
        total_missing += len(missing)

print(f'Pages: {count}')
print(f'Pages with missing sections: {pages_with_missing} (was 1076)')
print(f'Total missing sections: {total_missing} (was 3582)')
