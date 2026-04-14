import shutil
import argparse
import zipfile
import os
from pathlib import Path

def move_files(root_dir, suffix, target_subfolder):
    root = Path(root_dir)
    count = 0

    for file_path in root.rglob(f'*{suffix}'):
        try:
            parts = file_path.parts
            if 'assets' not in parts or 'textures' not in parts:
                continue

            texture_dir = None
            for parent in file_path.parents:
                if parent.name == 'textures':
                    texture_dir = parent
                    break

            if texture_dir is None:
                continue

            if target_subfolder in file_path.relative_to(texture_dir).parts:
                continue

            rel_path = file_path.relative_to(texture_dir)
            dest_path = texture_dir / target_subfolder / rel_path

            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(file_path), str(dest_path))
            count += 1

        except Exception as e:
            print(f"  [Error] Processing {file_path.name}: {e}")

    return count

def zip_folder(folder_path, output_path):
    folder_path = Path(folder_path)
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file in folder_path.rglob('*'):
            if file.is_file():
                zipf.write(file, arcname=file.relative_to(folder_path))

def main():
    parser = argparse.ArgumentParser(description="Unzip, organize textures, re-zip, and clean up.")
    parser.add_argument("zip_file", help="The path to the source .zip file")

    args = parser.parse_args()
    zip_path = Path(args.zip_file).resolve()

    if not zip_path.exists() or zip_path.suffix.lower() != '.zip':
        print(f"Error: File '{zip_path}' not found or is not a .zip file.")
        return

    temp_extract_dir = zip_path.parent / (zip_path.stem + "_temp_processing")
    output_zip_path = zip_path.parent / (zip_path.stem + "_processed.zip")

    try:
        print(f"1. Extracting '{zip_path.name}' to temporary folder...")
        if temp_extract_dir.exists():
            shutil.rmtree(temp_extract_dir)

        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_extract_dir)

        print(f"2. Organizing textures inside temp folder...")
        s_count = move_files(temp_extract_dir, "_s.png", "specular")
        n_count = move_files(temp_extract_dir, "_n.png", "normal")
        print(f"   - Moved {s_count} specular maps.")
        print(f"   - Moved {n_count} normal maps.")

        print(f"3. Re-packing into '{output_zip_path.name}'...")
        zip_folder(temp_extract_dir, output_zip_path)

    except Exception as e:
        print(f"\n[CRITICAL ERROR]: {e}")
        print("Cleanup may not have finished due to error.")
        return

    finally:
        if temp_extract_dir.exists():
            print(f"4. Cleaning up temporary files...")
            shutil.rmtree(temp_extract_dir)

    print("-" * 30)
    print("Success! Process completed.")
    print(f"New file location: {output_zip_path}")

if __name__ == "__main__":
    main()
