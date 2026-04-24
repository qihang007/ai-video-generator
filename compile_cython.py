from Cython.Build import cythonize
from setuptools import setup, Extension
import glob
import os
import sys

os.chdir(r"M:\桌面文件\auto-video-maker")

files = glob.glob('auto_video/*.py')
files = [f for f in files if '__pycache__' not in f and '.cp310' not in f and '.c' not in f and '.pyx' not in f]
print(f'Compiling {len(files)} files...')

extensions = [
    Extension(f"auto_video.{os.path.basename(f)[:-3]}", [f[:-2] + 'c'])
    for f in files
]

setup(
    name="auto_video",
    ext_modules=cythonize(extensions, compiler_directives={'language_level': '3'}),
    script_args=['build_ext', '--inplace']
)
