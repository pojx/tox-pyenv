"""tox-pyenv

Plugin for the tox_get_python_executable using tox's plugin system:

    https://testrun.org/tox/latest/plugins.html#tox.hookspecs.tox_get_python_executable

Modified to instead use `pyenv which` to locate the
appropriate python executable. This takes the place
of the standard behavior in tox. The built-in default
for the tox_get_python_exeucutable function
is the following (for sys.platform != 'win32'):

    @hookimpl
    def tox_get_python_executable(envconfig):
        return py.path.local.sysfind(envconfig.basepython)

which uses the 'py' package's sysfind():

    https://pylib.readthedocs.org/en/latest/path.html#py._path.local.LocalPath.sysfind

If `pyenv`'s shims are not at the very front of your path,
sysfind might lookup the global system version of python
instead of preferring a version specified by using `pyenv local`
or `pyenv global`. This plugin changes the way tox finds
your python executable to exclusively use `pyenv which`.

    https://github.com/yyuu/pyenv/blob/master/COMMANDS.md#pyenv-which

"""

# __about__
__title__ = 'tox-pyenv'
__summary__ = ('tox plugin that makes tox use `pyenv which` '
               'to find python executables')
__url__ = 'https://github.com/samstav/tox-pyenv'
__version__ = '1.1.0'
__author__ = 'Sam Stavinoha'
__email__ = 'smlstvnh@gmail.com'
__keywords__ = ['tox', 'pyenv', 'python']
__license__ = 'Apache License, Version 2.0'
# __about__


import logging
import subprocess

import py
from tox import hookimpl as tox_hookimpl

LOG = logging.getLogger(__name__)


class ToxPyenvException(Exception):

    """Base class for exceptions from this plugin."""


class PyenvMissing(ToxPyenvException, RuntimeError):

    """The pyenv program is not installed."""


class PyenvWhichFailed(ToxPyenvException):

    """Calling `pyenv which` failed."""


class PyenvInstallFailed(ToxPyenvException):

    """Calling `pyenv install` failed."""


@tox_hookimpl
def tox_get_python_executable(envconfig):
    """Return a python executable for the given python base name.

    The first plugin/hook which returns an executable path will determine it.

    ``envconfig`` is the testenv configuration which contains
    per-testenv configuration, notably the ``.envname`` and ``.basepython``
    setting.
    """

    def run_pyenv(command, err_string_on_os_error, log_string_on_os_error):
        pipe = None
        out = None
        cmd = None
        try:
            # pylint: disable=no-member
            pyenv = (getattr(py.path.local.sysfind('pyenv'), 'strpath', 'pyenv')
                     or 'pyenv')
            cmd = [pyenv, command, envconfig.basepython]
            pipe = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            out, err = pipe.communicate()
        except OSError:
            err = err_string_on_os_error
            LOG.warning(log_string_on_os_error)
        return pipe, out, err, cmd

    def find_using_pyenv():
        return run_pyenv(
            'which',
            err_string_on_os_error='\'pyenv\': command not found',
            log_string_on_os_error=
            "pyenv doesn't seem to be installed, you probably "
            "don't want this plugin installed either."
         )

    def install_using_pyenv():
        return run_pyenv(
            'install',
            err_string_on_os_error='install failed',
            log_string_on_os_error=
            "pyenv doesn't seem to be able to install "
            "the requested python version " + envconfig.basepython + "."
         )

    pipe, out, err, cmd = find_using_pyenv()
    # found installed
    if pipe and pipe.poll() == 0:
        return out.strip()
    # try installing
    if envconfig.tox_pyenv_auto_install:
        pipe, out, err, cmd = install_using_pyenv()
        if pipe and not err:
            pipe, out, err, cmd = find_using_pyenv()
            # found newly installed
            if pipe and pipe.poll() == 0:
                return out.strip()

    # cancel if no fallback
    if not envconfig.tox_pyenv_fallback:
        raise PyenvWhichFailed(err)
    LOG.debug("`%s` failed thru tox-pyenv plugin, falling back. "
              "STDERR: \"%s\" | To disable this behavior, set "
              "tox_pyenv_fallback=False in your tox.ini or use "
              " --tox-pyenv-no-fallback on the command line.",
              ' '.join([str(x) for x in cmd]), err)


def _setup_no_fallback(parser):
    """Add the option, --tox-pyenv-no-fallback.

    If this option is set, do not allow fallback to tox's built-in
    strategy for looking up python executables if the call to `pyenv which`
    by this plugin fails. This will allow the error to raise instead
    of falling back to tox's default behavior.
    """

    cli_dest = 'tox_pyenv_fallback'
    halp = ('If `pyenv which {basepython}` exits non-zero when looking '
            'up the python executable, do not allow fallback to tox\'s '
            'built-in default logic.')
    # Add a command-line option.
    tox_pyenv_group = parser.argparser.add_argument_group(
        title='{0} plugin options'.format(__title__),
    )
    tox_pyenv_group.add_argument(
        '--tox-pyenv-no-fallback', '-F',
        dest=cli_dest,
        default=True,
        action='store_false',
        help=halp
    )

    def _pyenv_fallback(testenv_config, value):
        cli_says = getattr(testenv_config.config.option, cli_dest)
        return cli_says or value

    # Add an equivalent tox.ini [testenv] section option.
    parser.add_testenv_attribute(
        name=cli_dest,
        type="bool",
        postprocess=_pyenv_fallback,
        default=False,
        help=('If `pyenv which {basepython}` exits non-zero when looking '
              'up the python executable, allow fallback to tox\'s '
              'built-in default logic.'),
    )


def _setup_auto_install(parser):
    """Add the option, --tox-pyenv-auto-install.

    If this option is set, do not allow fallback to tox's built-in
    strategy for looking up python executables if the call to `pyenv which`
    by this plugin fails. This will allow the error to raise instead
    of falling back to tox's default behavior.
    """

    cli_dest = 'tox_pyenv_auto_install'
    halp = ('If `pyenv which {basepython}` exits non-zero when looking '
            'up the python executable, try installing it with '
            '`pyenv install {basepython}`.')
    # Add a command-line option.
    tox_pyenv_group = parser.argparser.add_argument_group(
        title='{0} plugin options'.format(__title__),
    )
    tox_pyenv_group.add_argument(
        '--tox-pyenv-auto-install', '-I',
        dest=cli_dest,
        default=False,
        action='store_false',
        help=halp
    )

    def _pyenv_auto_install(testenv_config, value):
        cli_says = getattr(testenv_config.config.option, cli_dest)
        return cli_says or value

    # Add an equivalent tox.ini [testenv] section option.
    parser.add_testenv_attribute(
        name=cli_dest,
        type="bool",
        postprocess=_pyenv_auto_install,
        default=False,
        help=('If `pyenv which {basepython}` exits non-zero when looking '
              'up the python executable, try installing it with '
              '`pyenv install {basepython}`.'),
    )


@tox_hookimpl
def tox_addoption(parser):
    """Add command line option to the argparse-style parser object."""
    _setup_no_fallback(parser)
    _setup_auto_install(parser)
