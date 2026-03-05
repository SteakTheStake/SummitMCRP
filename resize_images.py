#!/usr/bin/env python3
"""
Image Resizer Script
Resizes all images in a directory to have shortest side of 512 pixels, maintaining aspect ratio.
"""

import os
import sys
from PIL import Image
from pathlib import Path

def resize_images(directory_path):
    """Resize all images in the specified directory to have shortest side of 512 pixels."""
    
    # Supported image formats
    supported_formats = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp'}
    
    target_short_side = 512
    
    # Convert to Path object
    directory = Path(directory_path)
    
    if not directory.exists():
        print(f"Error: Directory '{directory_path}' does not exist.")
        return False
    
    if not directory.is_dir():
        print(f"Error: '{directory_path}' is not a directory.")
        return False
    
    # Find all image files
    image_files = []
    for file_path in directory.iterdir():
        if file_path.is_file() and file_path.suffix.lower() in supported_formats:
            image_files.append(file_path)
    
    if not image_files:
        print(f"No supported image files found in '{directory_path}'.")
        return False
    
    print(f"Found {len(image_files)} images to resize...")
    
    # Process each image
    success_count = 0
    error_count = 0
    
    for image_file in image_files:
        try:
            # Open the image
            with Image.open(image_file) as img:
                # Get original dimensions
                width, height = img.size
                
                # Calculate new dimensions maintaining aspect ratio
                if width <= height:
                    # Width is the shortest side
                    new_width = target_short_side
                    scale_factor = target_short_side / width
                    new_height = int(height * scale_factor)
                else:
                    # Height is the shortest side
                    new_height = target_short_side
                    scale_factor = target_short_side / height
                    new_width = int(width * scale_factor)
                
                new_size = (new_width, new_height)
                
                # Resize using nearest-neighbor interpolation (no smoothing)
                # Preserve original mode to keep transparency
                resized_img = img.resize(new_size, Image.NEAREST)
                
                # Save the resized image, overwriting the original
                # Preserve original format and transparency
                resized_img.save(image_file)
                
                print(f"✓ Resized: {image_file.name} ({width}x{height} → {new_width}x{new_height})")
                success_count += 1
                
        except Exception as e:
            print(f"✗ Error resizing {image_file.name}: {e}")
            error_count += 1
    
    print(f"\nDone! {success_count} images resized successfully.")
    if error_count > 0:
        print(f"Failed to resize {error_count} images.")
    
    return error_count == 0

def main():
    """Main function to handle command line arguments."""
    
    if len(sys.argv) != 2:
        print("Usage: python resize_images.py <directory_path>")
        print("\nExample: python resize_images.py ./images")
        print("         python resize_images.py C:/Users/Name/Pictures")
        sys.exit(1)
    
    directory_path = sys.argv[1]
    
    # Confirm with user before proceeding
    print(f"This will resize ALL images in: {directory_path}")
    print("All images will be scaled so the shortest side is 512 pixels, maintaining aspect ratio.")
    print("The original files will be OVERWRITTEN.")
    
    response = input("Are you sure you want to continue? (y/N): ").strip().lower()
    if response not in ['y', 'yes']:
        print("Operation cancelled.")
        sys.exit(0)
    
    # Resize images
    success = resize_images(directory_path)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
