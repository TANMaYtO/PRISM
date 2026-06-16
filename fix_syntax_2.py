import os
import re

agents_dir = r"E:\se4cond agent\prism\agents"
agent_files = ["bug_detector.py", "logic_auditor.py", "security_scanner.py", "style_checker.py"]

for filename in agent_files:
    filepath = os.path.join(agents_dir, filename)
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    
    # We need to replace the literal newlines inside the quotes.
    # The broken string is:
    #     prompt = "## Pull Request Diffs
    # 
    # " + "
    # 
    # ".join(combined_prompts)
    
    # Let's just do a regex replace to catch any literal newlines inside standard quotes that I accidentally inserted
    # But wait, it's easier to just replace that specific block.
    
    broken_str = '    prompt = "## Pull Request Diffs\n\n" + "\n\n".join(combined_prompts)'
    fixed_str = '    prompt = "## Pull Request Diffs\\n\\n" + "\\n\\n".join(combined_prompts)'
    
    new_content = content.replace(broken_str, fixed_str)
    
    if new_content != content:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"Fixed string concat in {filename}")
    else:
        print(f"Could not find broken string in {filename}")
