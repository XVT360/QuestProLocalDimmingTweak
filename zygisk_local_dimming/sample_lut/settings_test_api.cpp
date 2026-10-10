// Offline-only library entry. The release contains ldctl, never this shim.
int ldctl_entry(int argc, char **argv);
extern "C" __attribute__((visibility("default")))
int test_ldctl(int argc, char **argv) { return ldctl_entry(argc, argv); }
