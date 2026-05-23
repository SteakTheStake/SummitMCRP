import os
import re
import shutil
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from PIL import Image

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    DND_AVAILABLE = True
except ImportError:
    DND_AVAILABLE = False


VALID_SIZES = [16, 32, 64, 128, 256, 512, 1024]


def clean_drop_paths(drop_data: str):
    """
    Handles drag/drop paths from tkinterdnd2.
    Supports paths with spaces wrapped in braces.
    """
    if not drop_data:
        return []

    # Matches either {C:/path with spaces/file.png} or plain paths
    matches = re.findall(r'\{([^}]*)\}|([^\s]+)', drop_data)
    paths = []
    for braced, plain in matches:
        p = braced or plain
        if p:
            paths.append(Path(p))
    return paths


def base_texture_name(path: Path):
    """
    Turns:
      end_stone.png -> end_stone
      end_stone_n.png -> end_stone
      end_stone_s.png -> end_stone
    """
    stem = path.stem
    if stem.endswith("_n") or stem.endswith("_s"):
        return stem[:-2]
    return stem


def classify_input_images(paths):
    """
    Finds base, normal, and specular images from dropped files.
    Expected:
      name.png
      name_n.png
      name_s.png
    """
    pngs = [Path(p) for p in paths if Path(p).suffix.lower() == ".png"]

    if len(pngs) < 3:
        raise ValueError("Drop at least 3 PNG files: base, _n, and _s.")

    grouped = {}

    for p in pngs:
        root = base_texture_name(p)
        grouped.setdefault(root, {})

        if p.stem.endswith("_n"):
            grouped[root]["normal"] = p
        elif p.stem.endswith("_s"):
            grouped[root]["specular"] = p
        else:
            grouped[root]["base"] = p

    complete = {
        name: group for name, group in grouped.items()
        if "base" in group and "normal" in group and "specular" in group
    }

    if not complete:
        raise ValueError(
            "Could not find a complete set named like:\n"
            "block.png\nblock_n.png\nblock_s.png"
        )

    return complete


def resize_to_grid(img: Image.Image, tile_size: int, grid_w: int, grid_h: int):
    """
    Resizes source image into a full CTM sheet sized:
      grid_w * tile_size by grid_h * tile_size
    """
    target_w = tile_size * grid_w
    target_h = tile_size * grid_h

    if img.size == (target_w, target_h):
        return img

    return img.resize((target_w, target_h), Image.Resampling.NEAREST)


def split_sheet_to_tiles(
    source_path: Path,
    output_dir: Path,
    suffix: str,
    tile_size: int,
    grid_w: int,
    grid_h: int
):
    """
    Splits one source sheet into numbered CTM tiles.

    suffix:
      ""   -> 0.png
      "_n" -> 0_n.png
      "_s" -> 0_s.png
    """
    with Image.open(source_path) as img:
        img = img.convert("RGBA")
        sheet = resize_to_grid(img, tile_size, grid_w, grid_h)

        tile_index = 0

        for y in range(grid_h):
            for x in range(grid_w):
                left = x * tile_size
                top = y * tile_size
                right = left + tile_size
                bottom = top + tile_size

                tile = sheet.crop((left, top, right, bottom))
                tile_name = f"{tile_index}{suffix}.png"
                tile.save(output_dir / tile_name)

                tile_index += 1


def write_properties_file(
    output_dir: Path,
    properties_name: str,
    match_tiles: str,
    grid_w: int,
    grid_h: int
):
    tile_count = grid_w * grid_h
    end_tile = tile_count - 1

    content = (
        f"tiles=0-{end_tile}\n"
        f"method=repeat\n"
        f"height={grid_h}\n"
        f"width={grid_w}\n"
        f"matchTiles={match_tiles}\n"
    )

    prop_path = output_dir / f"{properties_name}.properties"
    prop_path.write_text(content, encoding="utf-8")


def generate_repeat_ctm(
    image_set,
    block_name: str,
    output_root: Path,
    tile_size: int,
    grid_w: int,
    grid_h: int,
    make_optifine_structure: bool
):
    """
    image_set contains:
      base
      normal
      specular
    """
    if make_optifine_structure:
        output_dir = output_root / "assets" / "minecraft" / "optifine" / "ctm" / block_name
    else:
        output_dir = output_root / block_name

    output_dir.mkdir(parents=True, exist_ok=True)

    split_sheet_to_tiles(
        source_path=image_set["base"],
        output_dir=output_dir,
        suffix="",
        tile_size=tile_size,
        grid_w=grid_w,
        grid_h=grid_h
    )

    split_sheet_to_tiles(
        source_path=image_set["normal"],
        output_dir=output_dir,
        suffix="_n",
        tile_size=tile_size,
        grid_w=grid_w,
        grid_h=grid_h
    )

    split_sheet_to_tiles(
        source_path=image_set["specular"],
        output_dir=output_dir,
        suffix="_s",
        tile_size=tile_size,
        grid_w=grid_w,
        grid_h=grid_h
    )

    write_properties_file(
        output_dir=output_dir,
        properties_name=block_name,
        match_tiles=block_name,
        grid_w=grid_w,
        grid_h=grid_h
    )

    return output_dir


class RepeatCTMGui:
    def __init__(self, root):
        self.root = root
        self.root.title("Repeat CTM Tile Generator")
        self.root.geometry("680x520")
        self.root.minsize(620, 460)

        self.dropped_paths = []
        self.image_sets = {}

        self.tile_size_var = tk.IntVar(value=64)
        self.grid_w_var = tk.IntVar(value=3)
        self.grid_h_var = tk.IntVar(value=3)
        self.output_dir_var = tk.StringVar(value=str(Path.cwd() / "repeat_ctm_output"))
        self.structure_var = tk.BooleanVar(value=False)

        self.build_ui()

    def build_ui(self):
        main = ttk.Frame(self.root, padding=16)
        main.pack(fill="both", expand=True)

        title = ttk.Label(
            main,
            text="Repeat CTM Tile Generator",
            font=("Segoe UI", 16, "bold")
        )
        title.pack(anchor="w")

        desc = ttk.Label(
            main,
            text=(
                "Drop a complete image set named block.png, block_n.png, and block_s.png. "
                "The script splits/resizes them into Repeat CTM tiles."
            ),
            wraplength=620
        )
        desc.pack(anchor="w", pady=(6, 14))

        self.drop_box = tk.Listbox(
            main,
            height=9,
            selectmode="extended",
            bg="#1f1f1f",
            fg="#f2f2f2",
            highlightthickness=1,
            relief="flat"
        )
        self.drop_box.pack(fill="both", expand=True)

        self.drop_box.insert(
            "end",
            "Drag and drop PNG files here, or use Add Images..."
        )

        if DND_AVAILABLE:
            self.drop_box.drop_target_register(DND_FILES)
            self.drop_box.dnd_bind("<<Drop>>", self.on_drop)
        else:
            self.drop_box.insert(
                "end",
                "NOTE: tkinterdnd2 is not installed. Drag/drop is disabled."
            )

        button_row = ttk.Frame(main)
        button_row.pack(fill="x", pady=(10, 8))

        ttk.Button(button_row, text="Add Images", command=self.add_images).pack(side="left")
        ttk.Button(button_row, text="Clear", command=self.clear_images).pack(side="left", padx=(8, 0))

        settings = ttk.LabelFrame(main, text="Output Settings", padding=12)
        settings.pack(fill="x", pady=(8, 8))

        row1 = ttk.Frame(settings)
        row1.pack(fill="x", pady=4)

        ttk.Label(row1, text="Tile size:").pack(side="left")
        ttk.Combobox(
            row1,
            textvariable=self.tile_size_var,
            values=VALID_SIZES,
            width=8,
            state="readonly"
        ).pack(side="left", padx=(8, 18))

        ttk.Label(row1, text="Repeat width:").pack(side="left")
        ttk.Spinbox(
            row1,
            from_=1,
            to=16,
            textvariable=self.grid_w_var,
            width=6
        ).pack(side="left", padx=(8, 18))

        ttk.Label(row1, text="Repeat height:").pack(side="left")
        ttk.Spinbox(
            row1,
            from_=1,
            to=16,
            textvariable=self.grid_h_var,
            width=6
        ).pack(side="left", padx=(8, 0))

        row2 = ttk.Frame(settings)
        row2.pack(fill="x", pady=4)

        ttk.Label(row2, text="Output folder:").pack(side="left")
        ttk.Entry(row2, textvariable=self.output_dir_var).pack(side="left", fill="x", expand=True, padx=(8, 8))
        ttk.Button(row2, text="Browse", command=self.pick_output_dir).pack(side="left")

        row3 = ttk.Frame(settings)
        row3.pack(fill="x", pady=4)

        ttk.Checkbutton(
            row3,
            text="Create OptiFine-style folder structure: assets/minecraft/optifine/ctm/[block]",
            variable=self.structure_var
        ).pack(anchor="w")

        ttk.Button(
            main,
            text="Generate Repeat CTM",
            command=self.generate
        ).pack(fill="x", pady=(10, 0))

        self.status = ttk.Label(main, text="Ready.")
        self.status.pack(anchor="w", pady=(10, 0))

    def on_drop(self, event):
        paths = clean_drop_paths(event.data)
        self.add_paths(paths)

    def add_images(self):
        files = filedialog.askopenfilenames(
            title="Select base, _n, and _s PNG images",
            filetypes=[("PNG files", "*.png")]
        )
        self.add_paths([Path(f) for f in files])

    def add_paths(self, paths):
        valid = [Path(p) for p in paths if Path(p).suffix.lower() == ".png"]

        if not valid:
            messagebox.showwarning("No PNG files", "Only PNG files are supported.")
            return

        if not self.dropped_paths:
            self.drop_box.delete(0, "end")

        for p in valid:
            if p not in self.dropped_paths:
                self.dropped_paths.append(p)
                self.drop_box.insert("end", str(p))

        try:
            self.image_sets = classify_input_images(self.dropped_paths)
            self.status.config(text=f"Found {len(self.image_sets)} complete image set(s).")
        except Exception as e:
            self.status.config(text=str(e))

    def clear_images(self):
        self.dropped_paths.clear()
        self.image_sets.clear()
        self.drop_box.delete(0, "end")
        self.drop_box.insert("end", "Drag and drop PNG files here, or use Add Images...")
        self.status.config(text="Ready.")

    def pick_output_dir(self):
        folder = filedialog.askdirectory(title="Choose output folder")
        if folder:
            self.output_dir_var.set(folder)

    def generate(self):
        try:
            self.image_sets = classify_input_images(self.dropped_paths)

            tile_size = int(self.tile_size_var.get())
            grid_w = int(self.grid_w_var.get())
            grid_h = int(self.grid_h_var.get())
            output_root = Path(self.output_dir_var.get())

            if tile_size not in VALID_SIZES:
                raise ValueError("Choose a valid power-of-two tile size.")

            if grid_w <= 0 or grid_h <= 0:
                raise ValueError("Repeat width and height must be greater than 0.")

            created_dirs = []

            for block_name, image_set in self.image_sets.items():
                output_dir = generate_repeat_ctm(
                    image_set=image_set,
                    block_name=block_name,
                    output_root=output_root,
                    tile_size=tile_size,
                    grid_w=grid_w,
                    grid_h=grid_h,
                    make_optifine_structure=self.structure_var.get()
                )
                created_dirs.append(output_dir)

            msg = "Generated Repeat CTM output:\n\n" + "\n".join(str(p) for p in created_dirs)
            self.status.config(text="Generation complete.")
            messagebox.showinfo("Done", msg)

        except Exception as e:
            messagebox.showerror("Error", str(e))
            self.status.config(text=f"Error: {e}")


def main():
    if DND_AVAILABLE:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()

    app = RepeatCTMGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()