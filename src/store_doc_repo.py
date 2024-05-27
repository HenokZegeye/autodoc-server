import os
import pdb
import shutil
import time
from git import Repo
import tempfile
import stat

def on_rm_error(func, path, exc_info):
    os.chmod(path, stat.S_IWRITE)
    func(path)

def clone_and_replace():
    repo_url = os.environ['DOC_REPO_URL']
    target_dir = f'../data/documentation'
    
    temp_dir = tempfile.mkdtemp()

    try:
        # Step 1: Clone the repository into the temporary directory
        repo = Repo.clone_from(repo_url, temp_dir)
        repo.git.checkout(os.environ['DOC_REPO_TARGET_BRANCH'])

        # Step 2: If cloning is successful, delete the old directory
        if os.path.exists(target_dir):
            for _ in range(3):
                try:
                    shutil.rmtree(target_dir, onerror=on_rm_error)
                    break
                except PermissionError as e:
                    print(f"PermissionError: {e}. Retrying...")
                    time.sleep(1)
        else:
            raise Exception("Failed to delete the old directory after multiple attempts.")
        # Step 3: Move the temporary directory to the target location
        shutil.move(temp_dir, target_dir)
        
        print(f"Doc Repo successfully cloned to {target_dir}")

    except Exception as e:
        print(f"Failed to clone the repository: {e}")
        print("Retaining the existing data.")

    