from argparse import ArgumentParser
from pathlib import Path
import re
from typing import Dict, Tuple, Union

from box import Box
import numpy as np


def center_object(obj: np.ndarray):
    """Center the values along each dimension.

    The .txt files have 6 columns
    """
    centered_obj = obj.copy()
    # center along each dimension
    _, col = centered_obj.shape

    # only take the vertex information
    csize = col if col < 4 else col // 2
    centered_obj = centered_obj[:, :csize]

    for c in range(csize):
        if c == 2:
            pass
        # dimension min/max
        dim_min = obj[:, c].min()
        dim_max = obj[:, c].max()

        dim_center = dim_min + ((dim_max - dim_min) // 2)

        dim_shift = 0 - dim_center
        centered_obj[:, c] = obj[:, c] + dim_shift

    # works for pixels and voxels
    return np.hstack([centered_obj, obj[:, csize:]])


def get_boundary_fpath(fname: Path, **kwargs) -> str:
    extension = kwargs.get("extension", "")
    fpath = fname.parent
    new_path = fpath / "boundary" / fname.name

    if extension != "":
        if "." in extension:
            new_path = new_path.with_suffix(extension)
        else:
            new_path = new_path.with_suffix(f".{extension}")

    Path(new_path).parent.mkdir(parents=True, exist_ok=True)
    return new_path.as_posix()


def get_new_fpath(fname: Path, new_dir: str):
    extension = ".txt"
    data_dir = fname.parent
    path_ = data_dir / new_dir / fname.stem
    new_path = path_.with_suffix(extension)
    
    # Ensure the path to the file exists
    Path(new_path).parent.mkdir(parents=True, exist_ok=True)

    return new_path.as_posix()


def parse_cli() -> ArgumentParser:
    ap = ArgumentParser()
    ap.add_argument(
        "--image_path",
        "-i",
        dest="image_path",
        default="../data/source.png",
        required=True,
    )
    ap.add_argument(
        "--object_path",
        "-o",
        dest="obj_path",
        default="../data/source.obj",
        required=True,
    )
    ap.add_argument(
        "--boundary_path",
        "-b",
        dest="boundary_path",
        required=True,
    )
    ap.add_argument(
        "--chunk_path",
        "-c",
        dest="chunk_path",
        required=False,
    )
    ap.add_argument(
        "--debug",
        "-d",
        dest="debug",
        action="store_true",
    )
    ap.add_argument(
        "--skip_boundary",
        "-k",
        dest="skip_boundary",
        action="store_true",
    )
    args = ap.parse_args()
    args = Box(args.__dict__)

    return args


def preprocess_pixels(in_fpath: Path, center: bool = False) -> Tuple[np.ndarray, Path]:
    with open(in_fpath, "r") as pix:
        p_ = pix.read()

    pixels = re.findall("vt\ .*", p_)
    pixels = [p.replace("vt ", "").replace(" ", ",").split(",") for p in pixels]
    px = np.array(pixels, float)

    if center:
        px = center_object(px)
        fname_out = in_fpath.with_name(f"{in_fpath.stem}_centered.txt")
    else:
        fname_out = in_fpath
    return px, fname_out


def preprocess_voxels(
    in_fpath: Path, center: bool = False, trim_z: float = 1.0
) -> Tuple[np.ndarray, Path]:
    with open(in_fpath, "r") as vox:
        v_ = vox.read()

    voxels = re.findall("v\ .*", v_)
    voxels = [
        v.replace("v ", "").replace(" ", ",").replace("\n", "").split(",")
        for v in voxels
    ]
    vx = np.array(voxels, float)
    if center:
        vx = center_object(vx)
        fname_out = in_fpath.with_name(f"{in_fpath.stem}_centered.txt")
    else:
        fname_out = in_fpath

    trim_z = trim_z if trim_z <= 1.0 and trim_z >= 0.0 else 1.0
    if trim_z != 1.0:
        trim_min = vx[:, 2].min() * trim_z
        vx[:, 2] = np.maximum(vx[:, 2], trim_min)

    return vx, fname_out


def process_obj_file(in_fpath: Path):
    """Split the input .obj file into voxel and texture files.

    In order to know which voxel (3D) points we're manipulating,
    we also need to know the corresponding texture (2D) points.
    These are neatly organized by index in a Wavefront (.obj) file.
    According to Wikipedia's page on formatting Wavefront files
    (https://en.wikipedia.org/wiki/Wavefront_.centered_objfile), there is
    a clean way of parsing out the voxels from the texture points
    using regular expressions.
    """
    voxel_re = re.compile("v\ ")
    texture_re = re.compile("vt\ ")

    dirpath_out = in_fpath
    fname_voxel = dirpath_out.with_name(f"{in_fpath.stem}_voxels.txt")
    fname_texture = dirpath_out.with_name(f"{in_fpath.stem}_texture.txt")

    with open(in_fpath.resolve().as_posix(), "r") as f:
        with open(fname_voxel.resolve().as_posix(), "w") as two, open(
            fname_texture.resolve().as_posix(), "w"
        ) as three:
            for line in f.readlines():
                if voxel_re.search(line):
                    two.write(f"{line[2:]}")

                if texture_re.search(line):
                    three.write(f"{line[3:]}")


def update_vertex_indices(face_string: str, mapping: Dict[int, int]) -> str:
    """Update the vertex indices to adjust for points I filtered out.

    Args:
        face_string (str): A string in the form `f int1/int1 int2/int2 int3/int3`.
        mapping (Dict[int, int]): A mapping between a vertex's index in the input file and output file.

    Returns:
        (str) A string in the form `f int1/int1 int2/int2 int3/int3`.

    """
    updated_idxs = "f "
    fs = [int(x.split("/")[0]) for x in face_string[2:].strip().split(" ")]
    for idx in fs:
        updated_idxs += str(mapping[idx]) + "/" + str(mapping[idx]) + " "
    updated_idxs = updated_idxs[:-1]
    return updated_idxs + "\n"


def write_points(
    fpath_out: Path,
    keypoints: Dict[str, Dict[str, Union[int, np.ndarray]]],
    point_dir: str = "keypoints",
):
    fpath_metrics = get_new_fpath(fpath_out, point_dir)
    with open(fpath_metrics, "w+") as fmp:
        for k, v in keypoints.items():
            vox = v["xyz"]
            fmp.write(f"{k} {' '.join([str(v) for v in vox])}\n")


def write_object(
    fpath_out: Path,
    fpath_obj: Path,
    index: np.ndarray,
    texture: np.ndarray,
    vertices: np.ndarray,
    **kwargs,
) -> None:
    """Create an .obj file using the texture and vertices data."""
    d = {"prefix": "masked", "suffix": "object", "extension": "obj"}
    d.update(kwargs)

    # map to translate unfiltered index values to filtered values
    idx_mapping = {}

    get_vertex_indices = lambda a: set(
        [int(x.split("/")[0]) for x in a[2:].strip().split(" ")]
    )

    fpath_selected = get_boundary_fpath(fpath_out, **d)

    with open(fpath_selected, "w") as s:
        # TODO: Should I include a 'material' .mtl file in the header?
        # create an index set
        index_ = set(index)
        # write vertices (3D) first
        for i, idx in enumerate(index):
            line = vertices[idx]
            # indices start at 1 for .obj files
            idx_mapping[idx] = i + 1
            s.write(f"v {' '.join([str(s) for s in line])}\n")

        # write texture (2D) second
        for lin in texture[index]:
            s.write(f"vt {' '.join([str(s) for s in lin])}\n")

        with open(fpath_obj, "r") as f_obj:
            read = f_obj.read()
            # two different WaveFront object face formats. This makes sure both use
            # cases are accounted for
            format1 = re.findall("(f(?:\ \d*\/\d*\/\d*){3}\\n)", read)
            format2 = re.findall("(f(?:\ \d*\/\d*){3}\\n)", read)
            format = format1 if len(format1) > len(format2) else format2

            # for every face in the mesh...
            for face_idxs in format:
                vtx = get_vertex_indices(face_idxs)

                # make sure all the face vertices are within the boundary
                if len(vtx.intersection(index_)) == 3:
                    updated_idxs = update_vertex_indices(face_idxs, idx_mapping)
                    s.write(updated_idxs)
