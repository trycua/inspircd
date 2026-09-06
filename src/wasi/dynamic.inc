// SPDX-License-Identifier: GPL-2.0-only
#include "inspircd.h"
#include "dynamic.h"
#include "wasi/static.h"

DLLManager::DLLManager(const std::string& name) : libname(name) { }
DLLManager::~DLLManager() = default;
ModulePtr DLLManager::CallInit()
{
    const auto name = libname.substr(libname.find_last_of('/') + 1);
    const auto& modules = WasiStaticModules();
    auto it = modules.find(name);
    if (it == modules.end())
    {
        err = "Module is not statically linked into this WASI build";
        return nullptr;
    }
    return it->second()->Share();
}
void* DLLManager::GetSymbol(const char* name) const { return nullptr; }
void DLLManager::RetrieveLastError() { }
