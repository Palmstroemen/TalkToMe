# SPDX-License-Identifier: LGPL-2.1-or-later
import os

from ttm_core import install


def test_venv_lives_in_the_user_folder():
    assert install.venv_dir("/u/TalkToMe") == os.path.join("/u/TalkToMe", "venv")
    assert install.venv_python("/v") == os.path.join("/v", "bin", "python")
    assert install.venv_python("/v", windows=True) == os.path.join("/v", "Scripts", "python.exe")


def test_default_python_prefers_the_user_folder():
    new = install.venv_python(install.venv_dir("/u"))
    old = install.venv_python(os.path.join("/addon/service", ".venv"))
    assert install.default_python("/u", "/addon/service", exists=lambda p: False) == new
    assert install.default_python("/u", "/addon/service", exists=lambda p: p == new) == new
    assert install.default_python("/u", "/addon/service", exists=lambda p: True) == new


def test_default_python_falls_back_to_a_venv_in_the_addon():
    old = install.venv_python(os.path.join("/addon/service", ".venv"))
    assert install.default_python("/u", "/addon/service", exists=lambda p: p == old) == old


def test_search_path_leaves_out_the_appimage():
    path = os.pathsep.join(["/tmp/.mount_FreeCA1/usr/bin", "/usr/local/bin", "/usr/bin"])
    assert install.search_path(path, appdir="/tmp/.mount_FreeCA1") == ["/usr/local/bin", "/usr/bin"]
    assert install.search_path(path) == ["/tmp/.mount_FreeCA1/usr/bin", "/usr/local/bin", "/usr/bin"]


def test_parse_version():
    assert install.parse_version("3.10\n") == (3, 10)
    assert install.parse_version("") is None
    assert install.parse_version("Python was not found") is None


def files(*paths):
    return lambda p: p in paths


def test_find_python_takes_the_first_new_enough():
    versions = {"/usr/local/bin/python3": (3, 8), "/usr/bin/python3": (3, 12)}
    found = install.find_python(["/usr/local/bin", "/usr/bin"], lambda program, args: versions.get(program),
                                isfile=files(*versions))
    assert found == ("/usr/bin/python3", [], (3, 12))


def test_find_python_none_when_too_old_or_missing():
    assert install.find_python(["/usr/bin"], lambda program, args: (3, 8), isfile=files("/usr/bin/python3")) is None
    assert install.find_python(["/usr/bin"], lambda program, args: (3, 12), isfile=files()) is None


def test_find_python_skips_python_of_an_app_bundle():
    bundle = "/Applications/FreeCAD.app/Contents/Resources/bin"
    found = install.find_python([bundle, "/usr/bin"], lambda program, args: (3, 11),
                                isfile=files(bundle + "/python3", "/usr/bin/python3"))
    assert found[0] == "/usr/bin/python3"


def test_find_python_on_windows_uses_the_launcher_and_skips_the_store_alias():
    store = r"C:\Users\a\AppData\Local\Microsoft\WindowsApps"
    windows = r"C:\Windows"
    found = install.find_python([store, windows], lambda program, args: (3, 12), windows=True,
                                isfile=files(os.path.join(store, "python.exe"), os.path.join(windows, "py.exe")),
                                join=os.path.join)
    assert found == (os.path.join(windows, "py.exe"), ["-3"], (3, 12))


def test_install_steps_create_the_venv_only_once():
    steps = install.install_steps(("/usr/bin/python3", []), "/u/venv", "/addon/service/requirements.txt",
                                  have_venv=False)
    assert [s[0] for s in steps] == ["venv", "packages"]
    assert steps[0][1:] == ("/usr/bin/python3", ["-m", "venv", "/u/venv"])
    assert steps[1][1] == install.venv_python("/u/venv")
    assert steps[1][2][:3] == ["-m", "pip", "install"]
    assert steps[1][2][-2:] == ["-r", "/addon/service/requirements.txt"]
    again = install.install_steps(None, "/u/venv", "/addon/service/requirements.txt", have_venv=True)
    assert [s[0] for s in again] == ["packages"]


def test_diagnose_known_problems():
    assert install.diagnose("The virtual environment was not created successfully because ensurepip "
                            "is not available.  On Debian/Ubuntu systems, ...") == ["venv"]
    assert install.diagnose("/usr/bin/python3: No module named venv") == ["venv"]
    assert install.diagnose("OSError: PortAudio library not found") == ["portaudio"]
    assert install.diagnose("Failed to establish a new connection: [Errno -3] Temporary failure in name "
                            "resolution") == ["network"]
    assert install.diagnose("ERROR: Could not install packages due to an OSError: [Errno 28] No space "
                            "left on device") == ["disk"]
    assert install.diagnose("ERROR: No matching distribution found for ctranslate2") == ["python_version"]
    assert install.diagnose("Successfully installed numpy-2.2.6") == []
