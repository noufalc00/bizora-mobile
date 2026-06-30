import os

# Name of the output text file
output_filename = "faizan_pro_codebase.txt"

# Get the directory where this script is running
current_dir = os.path.dirname(os.path.abspath(__file__))

with open(output_filename, 'w', encoding='utf-8') as outfile:
    outfile.write("FAIZAN PRO ACCOUNTING - FULL CODEBASE\n")
    outfile.write("="*50 + "\n\n")
    
    # Walk through all folders and files in the directory
    for root, dirs, files in os.walk(current_dir):
        # Optional: skip virtual environments or cache folders to save space
        if '.venv' in root or '__pycache__' in root:
            continue
            
        for file in files:
            # Only grab Python files, and don't include this combiner script itself
            if file.endswith(".py") and file != "combine_code.py":
                filepath = os.path.join(root, file)
                relative_path = os.path.relpath(filepath, current_dir)
                
                # Write a clear header for the file
                outfile.write(f"\n\n{'='*50}\n")
                outfile.write(f"FILE: {relative_path}\n")
                outfile.write(f"{'='*50}\n\n")
                
                # Read the actual code and append it
                try:
                    with open(filepath, 'r', encoding='utf-8') as infile:
                        outfile.write(infile.read())
                except Exception as e:
                    outfile.write(f"Error reading file: {e}\n")

print(f"Success! All your code has been combined into: {output_filename}")
