import errno
import os
import sys

import seccomp

policy = seccomp.SyscallFilter(defaction=seccomp.ALLOW)
policy.add_rule(seccomp.ERRNO(errno.EPERM), "ptrace")
policy.load()

os.execvp(sys.argv[1], sys.argv[1:])