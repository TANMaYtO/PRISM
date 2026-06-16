import os

files = [
    'agents/bug_detector.py',
    'agents/logic_auditor.py',
    'agents/security_scanner.py',
    'agents/style_checker.py'
]

for f in files:
    with open(f, 'r', encoding='utf-8') as file:
        content = file.read()
    
    start_idx = content.find('def _parse_findings(raw: str, agent_source: str)')
    end_idx = content.find('cleaned = raw.strip()') + len('cleaned = raw.strip()')
    
    if start_idx != -1 and end_idx != -1:
        old_logic = content[start_idx:end_idx]
        replacement = '''def _parse_findings(raw: Any, agent_source: str) -> list[dict[str, Any]]:
    \"\"\"Parse LLM output into a list of finding dicts.\"\"\"
    if isinstance(raw, list):
        if raw and isinstance(raw[0], dict) and "text" in raw[0]:
            raw = raw[0]["text"]
        else:
            raw = str(raw)
    
    if not isinstance(raw, str):
        raw = str(raw)

    cleaned = raw.strip()'''
        
        content = content.replace(old_logic, replacement)
        
        # also replace 'raw: str' to 'raw: Any' in the typing if needed, wait, the replacement covers the whole def.
        with open(f, 'w', encoding='utf-8') as file:
            file.write(content)
        print(f'Patched {f}')

with open('agents/synthesizer.py', 'r', encoding='utf-8') as file:
    content = file.read()

old_synth = 'summary = response.content.strip()'
new_synth = '''raw = response.content
    if isinstance(raw, list):
        if raw and isinstance(raw[0], dict) and "text" in raw[0]:
            raw = raw[0]["text"]
        else:
            raw = str(raw)
    if not isinstance(raw, str):
        raw = str(raw)
    summary = raw.strip()'''

if old_synth in content:
    content = content.replace(old_synth, new_synth)
    with open('agents/synthesizer.py', 'w', encoding='utf-8') as file:
        file.write(content)
    print('Patched synthesizer.py')
