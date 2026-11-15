import os
import warnings

from setuptools import setup

try:
    from setuptools.command.bdist_wheel import bdist_wheel as _bdist_wheel
except ImportError:
    from wheel.bdist_wheel import bdist_wheel as _bdist_wheel  # type: ignore


class bdist_wheel(_bdist_wheel):
    """
    Custom bdist_wheel command supporting optional platform-specific wheel tagging
    via the BSM_WHEEL_PLAT_NAME environment variable, while defaulting to a
    multi-platform py3-none-any wheel when both Linux and Windows amd64 dummy
    binaries are bundled in package data.
    """

    def finalize_options(self) -> None:
        super().finalize_options()
        plat_override = os.environ.get("BSM_WHEEL_PLAT_NAME")
        if plat_override:
            self.plat_name = plat_override
            self.root_is_pure = False

    def get_tag(self):
        python, abi, plat = super().get_tag()
        plat_override = os.environ.get("BSM_WHEEL_PLAT_NAME")
        if plat_override:
            return "py3", "none", plat_override
        return python, abi, plat


if __name__ == "__main__":
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        setup(cmdclass={"bdist_wheel": bdist_wheel})
