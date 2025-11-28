from Cython.Build import cythonize
from setuptools import setup, Extension
import platform, os, shutil, tempfile

class Compiler:

    def __init__ ( self ):

        self.source_path = None
        self.output_dir  = None
        self.module_name = None

    def set_options ( self, source_path: str, output_dir: str, module_name: str = None ):

        self.source_path = source_path
        self.output_dir  = output_dir
        self.module_name = module_name

    def execute ( self, file_path: str ):

        module_name  = self.module_name or os.path.splitext(os.path.basename(file_path))[0]
        source_abs   = os.path.abspath(file_path)
        sandbox_root = tempfile.mkdtemp(prefix="cybuild_")
        sandbox_file = os.path.join(sandbox_root, os.path.basename(source_abs))
    
        shutil.copy2(source_abs, sandbox_file)
        build_temp = tempfile.mkdtemp(prefix="cytemp_")

        ext = ".pyd" if os.name == "nt" else ".so"
        output_file = os.path.join(self.output_dir, f"{module_name}{ext}")

        is_windows   = platform.system() == "Windows"
        compile_args = ["/O2"] if is_windows else ["-O3", "-march=native", "-ffast-math", "-fomit-frame-pointer"]
        link_args    = [] if is_windows else ["-s"]

        ext_modules = cythonize(
            [
                Extension(
                    name=module_name,
                    sources=[sandbox_file],
                    libraries=["m"],
                    extra_compile_args=compile_args,
                    extra_link_args=link_args,
                )
            ],
            compiler_directives={
                "language_level": 3,
                "boundscheck": False,
                "wraparound": False,
                "cdivision": True,
                "initializedcheck": False,
                "nonecheck": False,
            },
            annotate=False
        )

        setup(
            name=module_name,
            ext_modules=ext_modules,
            script_args=[
                "build_ext",
                "--build-lib", self.output_dir,
                f"--build-temp={build_temp}",
            ],
            options={"build": {"build_base": build_temp}},
        )

        if not os.path.exists(output_file):
            for f in os.listdir(self.output_dir):
                if f.startswith(module_name) and f.endswith(ext):
                    output_file = os.path.join(self.output_dir, f)
                    break

        shutil.rmtree(sandbox_root, ignore_errors=True)
        shutil.rmtree(build_temp, ignore_errors=True)

        return output_file

    def build ( self ):

        files = []
        source_path = os.path.abspath(self.source_path)

        if os.path.isdir(source_path):
            files = [os.path.join(source_path, f) for f in os.listdir(source_path) if f.endswith((".py", ".pyx"))]
            self.output_dir = self.output_dir or os.path.join(source_path, "__build__")
    
        elif os.path.isfile(source_path):
            files = [source_path]
            self.output_dir = self.output_dir or os.path.dirname(source_path)

        if not files: return []

        self.output_dir = os.path.abspath(self.output_dir)
        os.makedirs(self.output_dir, exist_ok=True)

        outputs = [self.execute(file) for file in files]
        return [f for f in outputs if f and os.path.exists(f)]
