import zlib
import struct
import os

git_dir = r"C:\Users\26726\WorkBuddy\2026-06-22-10-40-26\caishuixitong\.git"

def read_object(sha):
    """Read a git object by its SHA hash."""
    path = os.path.join(git_dir, "objects", sha[:2], sha[2:])
    try:
        with open(path, "rb") as f:
            compressed = f.read()
        data = zlib.decompress(compressed)
        # First null byte separates header from content
        header_end = data.index(b'\x00')
        header = data[:header_end].decode('ascii')
        content = data[header_end+1:]
        obj_type, _ = header.split(' ')
        return obj_type, content
    except FileNotFoundError:
        return None, None

def find_blob_in_tree(tree_content, target_path):
    """Traverse a tree to find a blob at target_path."""
    parts = target_path.split('/')
    current = tree_content
    obj_type = 'tree'
    
    for i, part in enumerate(parts):
        if obj_type != 'tree':
            return None
        found = False
        pos = 0
        while pos < len(current):
            # Parse tree entry: "mode name\0" followed by 20-byte SHA
            space = current.index(b' ', pos)
            mode = current[pos:space].decode('ascii')
            
            null_byte = current.index(b'\x00', space)
            name = current[space+1:null_byte].decode('ascii')
            
            sha = current[null_byte+1:null_byte+21].hex()
            
            if name == part:
                if i == len(parts) - 1:
                    return sha, mode
                # Read next level
                obj_type, current = read_object(sha)
                found = True
                break
            
            pos = null_byte + 21
        
        if not found:
            return None
    
    return None

# Get HEAD commit
with open(os.path.join(git_dir, "HEAD")) as f:
    head = f.read().strip()

if head.startswith("ref: "):
    ref_path = head[5:]
    with open(os.path.join(git_dir, ref_path)) as f:
        commit_sha = f.read().strip()
else:
    commit_sha = head

# Read commit to get tree
obj_type, commit_data = read_object(commit_sha)
if obj_type != 'commit':
    print(f"Expected commit, got {obj_type}")
    exit(1)

commit_text = commit_data.decode('ascii', errors='replace')
# Find tree line
for line in commit_text.split('\n'):
    if line.startswith('tree '):
        tree_sha = line[5:]
        break

# Find the blob
obj_type, tree_data = read_object(tree_sha)
result = find_blob_in_tree(tree_data, "static/js/tax-doc-analysis.js")

if result:
    blob_sha, mode = result
    obj_type, blob_data = read_object(blob_sha)
    if obj_type == 'blob':
        output = r"C:\Users\26726\WorkBuddy\2026-06-22-10-40-26\caishuixitong\static\js\tax-doc-analysis.js"
        with open(output, "wb") as f:
            f.write(blob_data)
        print(f"Restored {len(blob_data)} bytes to {output}")
    else:
        print(f"Expected blob, got {obj_type}")
else:
    print("File not found in git tree")
