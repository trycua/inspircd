// SPDX-License-Identifier: GPL-2.0-only
#include <cstdio>
#include <stdexcept>
#include <string>

// An allocating user exception with temporaries catches runtime defects which
// a same-frame std::runtime_error smoke test misses (WasmEdge 0.17.1).
struct ConfigError : std::exception
{
    const std::string reason;
    explicit ConfigError(const std::string& text) : reason(text) { }
    const char* what() const noexcept override { return reason.c_str(); }
};

__attribute__((noinline)) void fail(const std::string& id)
{
    std::string local = "an allocating local destroyed during cross-frame unwinding";
    throw ConfigError(id + " is not a valid server ID; preserve exception construction and cleanup");
}

int main()
{
    for (int attempt = 0; attempt < 1000; ++attempt)
    {
        try { fail("invalid"); }
        catch (const ConfigError& error)
        {
            if (std::string(error.what()).find("invalid is not a valid server ID") != 0)
                return 3;
            continue;
        }
        return 4;
    }
    int destroyed = 0;
    struct Guard { int& count; ~Guard() { ++count; } };
    try
    {
        Guard guard{destroyed};
        try { throw std::runtime_error("wasi-unwind"); }
        catch (...) { throw; }
    }
    catch (const std::exception& error)
    {
        if (destroyed != 1 || std::string(error.what()) != "wasi-unwind")
            return 1;
        std::puts("PASS: C++ exception matching, rethrow, and destructor unwinding");
        return 0;
    }
    return 2;
}
