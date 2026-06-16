import os

agents_dir = r"E:\se4cond agent\prism\agents"
agent_files = ["bug_detector.py", "logic_auditor.py", "security_scanner.py", "style_checker.py"]

for filename in agent_files:
    filepath = os.path.join(agents_dir, filename)
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    
    # We need to replace: f"### File: {diff_file.filename} ... {context_str}")
    # with triple quotes: f\"\"\"### File: {diff_file.filename} ... {context_str}\"\"\"
    
    import re
    # The broken string starts with f"### File: and ends with {context_str}")
    
    new_content = content.replace(
        'f"### File: {diff_file.filename}\n\n```diff\n{diff_file.patch}\n```\n\nContext:\n{context_str}")',
        'f\"\"\"### File: {diff_file.filename}\\n\\n```diff\\n{diff_file.patch}\\n```\\n\\nContext:\\n{context_str}\"\"\")'
    )
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(new_content)
        
    print(f"Fixed syntax error in {filename}")
