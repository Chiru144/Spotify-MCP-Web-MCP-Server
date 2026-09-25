import re
with open('mcp-soundtrack-app/templates/index.html', 'r', encoding='utf-8') as f:
    text = f.read()
text = re.sub(r' data-vibe="\$\{.*?\}\"', '', text)
text = re.sub(r'if \(s\.vibe\) \{\s*card\.setAttribute\(\'data-vibe\', s\.vibe\);\s*\}', '', text)
text = text.replace('applyVibeFilter();', '')
text = text.replace('applyVibeFilter(); // re-apply vibe after render', '')
with open('mcp-soundtrack-app/templates/index.html', 'w', encoding='utf-8') as f:
    f.write(text)
