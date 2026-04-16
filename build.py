from poetry_dynamic_versioning import plugin


def get_version():
    return plugin.get_version()


def build_editable(wheel, build_dir):
    plugin.apply_wheel(wheel, build_dir)


def build_wheel(wheel, build_dir):
    plugin.apply_wheel(wheel, build_dir)


def build_sdist(sdist, build_dir):
    plugin.apply_sdist(sdist, build_dir)
