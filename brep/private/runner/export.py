# SPDX-License-Identifier: Apache-2.0
"""What the CAD runners share, with OCP alone (issue #15).

Both runners load and call part scripts, read the epoch and write STL with
it. The STEP writer here is the CadQuery runner's; the build123d runner
keeps build123d's, whose XCAF export names the children of an assembly.
"""

import datetime
import importlib.util
import os
import sys
import traceback


class PartError(Exception):
    """A part script that cannot be built; the message names it."""


def load_part(path):
    """Imports the part script at path as the module `part`.

    The module is in sys.modules while it runs, as an imported module is,
    so that dataclasses and pickling find it. The script's directory is on
    sys.path, so it can import its neighbors.
    """
    spec = importlib.util.spec_from_file_location("part", path)
    if spec is None or spec.loader is None:
        raise PartError("%s: cannot load it as a Python file" % path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["part"] = module
    sys.path.insert(0, os.path.dirname(os.path.abspath(path)))
    try:
        spec.loader.exec_module(module)
    except Exception as e:
        traceback.print_exc()
        raise PartError("%s: importing it failed: %s: %s" % (path, type(e).__name__, e))
    return module


def call_build(path, params):
    """Calls the build(params) function of the part script at path."""
    module = load_part(path)
    fn = getattr(module, "build", None)
    if not callable(fn):
        raise PartError("%s defines no build(params) function" % path)
    try:
        return fn(params)
    except Exception as e:
        traceback.print_exc()
        raise PartError("%s: build() failed: %s: %s" % (path, type(e).__name__, e))


def epoch_timestamp():
    """SOURCE_DATE_EPOCH as an ISO 8601 time in UTC, as STEP headers have it."""
    raw = os.environ.get("SOURCE_DATE_EPOCH", "0")
    try:
        t = int(raw)
    except ValueError:
        raise PartError("SOURCE_DATE_EPOCH=%r is not a number of seconds" % raw)
    if t < 0:
        raise PartError("SOURCE_DATE_EPOCH=%d is before 1970" % t)
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def write_step(shape, name, path, timestamp, system):
    """Writes the OCP shape as STEP, named name, at timestamp, from system.

    The product and the header's FILE_NAME are name, not the file's path,
    so the file holds no path of the build; the header's time is timestamp,
    and its originating system is system.
    """
    from OCP.APIHeaderSection import APIHeaderSection_MakeHeader
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.Interface import Interface_Static
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Controller, STEPControl_Writer
    from OCP.TCollection import TCollection_HAsciiString

    STEPControl_Controller.Init_s()
    Interface_Static.SetCVal_s("write.step.unit", "MM")
    Interface_Static.SetCVal_s("write.step.product.name", name)
    Interface_Static.SetIVal_s("write.surfacecurve.mode", 1)
    writer = STEPControl_Writer()
    if writer.Transfer(shape, STEPControl_AsIs) != IFSelect_RetDone:
        raise PartError("transferring the shape to STEP failed")
    header = APIHeaderSection_MakeHeader(writer.Model())
    header.SetName(TCollection_HAsciiString(name))
    header.SetTimeStamp(TCollection_HAsciiString(timestamp))
    header.SetOriginatingSystem(TCollection_HAsciiString(system))
    if writer.Write(path) != IFSelect_RetDone:
        raise PartError("writing the STEP file failed")


def write_stl(shape, path, tolerance, angular_tolerance):
    """Writes the OCP shape as binary STL, meshed with parallel meshing off.

    Parallel meshing may order the triangles differently from run to run.
    """
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.BRepTools import BRepTools
    from OCP.StlAPI import StlAPI_Writer

    # Drop any triangulation the part script made, maybe in parallel; the
    # constructor meshes once, with parallel meshing off.
    BRepTools.Clean_s(shape)
    mesh = BRepMesh_IncrementalMesh(shape, tolerance, False, angular_tolerance, False)
    if not mesh.IsDone():
        raise PartError("meshing for STL failed")
    writer = StlAPI_Writer()
    writer.ASCIIMode = False
    if not writer.Write(shape, path):
        raise PartError("writing the STL failed")
