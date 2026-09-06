// SPDX-License-Identifier: GPL-2.0-only
#pragma once

const std::map<std::string, Module* (*)()>& WasiStaticModules();
