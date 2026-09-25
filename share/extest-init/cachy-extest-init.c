/*
 * Preloaded ahead of libextest into the console-mode Steam client.
 *
 * libextest builds its virtual mouse the first time Steam sends any fake input,
 * and sizes the device's absolute axes by asking the Wayland compositor named in
 * WAYLAND_DISPLAY for its outputs. It unwraps both answers: with no
 * WAYLAND_DISPLAY it panics with NoCompositor, and against gamescope's own
 * socket, which has no xdg-output, it panics on a None. A panic in a preload is
 * an abort of the whole client, so the first trackpad movement over Discord
 * took Steam down, and Steam Input and the session's apps with it.
 *
 * Console mode keeps WAYLAND_DISPLAY away from Steam on purpose (games would
 * open their Vulkan windows on it), so this builds the device up front instead,
 * in the Steam client only, pointed at the desktop's compositor for the one call
 * that needs it. Constructors run before the client starts a thread, so the
 * environment can be changed safely here, and it is put back before anything
 * can inherit it.
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

#define HOST_VAR "CACHY_CONSOLE_EXTEST_WAYLAND"
#define CLIENT_TAIL "/ubuntu12_32/steam"

typedef int (*relative_motion_fn)(void *, int, int, unsigned long);

/* steam.sh and the games Steam starts inherit the preload too. */
static int is_steam_client(void)
{
    char exe[PATH_MAX];
    ssize_t n = readlink("/proc/self/exe", exe, sizeof exe - 1);
    size_t tail = strlen(CLIENT_TAIL);
    if (n <= 0)
        return 0;
    exe[n] = '\0';
    return (size_t)n >= tail && strcmp(exe + n - tail, CLIENT_TAIL) == 0;
}

static int compositor_answers(const char *name)
{
    struct sockaddr_un addr = { .sun_family = AF_UNIX };
    const char *runtime = getenv("XDG_RUNTIME_DIR");
    int fd, ok, len;
    if (name[0] == '/')
        len = snprintf(addr.sun_path, sizeof addr.sun_path, "%s", name);
    else if (runtime)
        len = snprintf(addr.sun_path, sizeof addr.sun_path, "%s/%s", runtime, name);
    else
        return 0;
    if (len < 0 || (size_t)len >= sizeof addr.sun_path)
        return 0;
    fd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
    if (fd < 0)
        return 0;
    ok = connect(fd, (struct sockaddr *)&addr, sizeof addr) == 0;
    close(fd);
    return ok;
}

/* The same symbol from anything but libextest would be libXtst's, which
 * dereferences the display this passes as NULL. */
static relative_motion_fn extest_motion(void)
{
    Dl_info info;
    void *sym = dlsym(RTLD_DEFAULT, "XTestFakeRelativeMotionEvent");
    if (!sym || !dladdr(sym, &info) || !info.dli_fname)
        return NULL;
    return strstr(info.dli_fname, "libextest") ? (relative_motion_fn)sym : NULL;
}

__attribute__((constructor)) static void build_extest_device(void)
{
    char host[128];
    const char *value = getenv(HOST_VAR);
    relative_motion_fn motion;

    if (!value || !*value || !is_steam_client())
        return;
    snprintf(host, sizeof host, "%s", value);
    unsetenv(HOST_VAR);

    if (getenv("WAYLAND_DISPLAY") || access("/dev/uinput", W_OK) != 0
        || !compositor_answers(host))
        return;
    motion = extest_motion();
    if (!motion)
        return;

    setenv("WAYLAND_DISPLAY", host, 1);
    motion(NULL, 0, 0, 0);
    unsetenv("WAYLAND_DISPLAY");
}
