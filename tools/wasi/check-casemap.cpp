// SPDX-License-Identifier: GPL-2.0-only
// Include the implementation to test both word sizes without server startup.
#include "../../src/casemap.cpp"

int main()
{
    alignas(16) unsigned char aligned[128];
    unsigned char unaligned[144];
    for (size_t index = 0; index < sizeof(aligned); ++index)
        aligned[index] = static_cast<unsigned char>(index + 32);
    for (int length = 0; length <= 128; ++length)
    {
        const auto expected = MURMUR_HASH(aligned, length, 0x1234);
        for (size_t offset = 0; offset < 16; ++offset)
        {
            memcpy(unaligned + offset, aligned, length);
            if (MURMUR_HASH(unaligned + offset, length, 0x1234) != expected)
                return 1;
        }
    }
    puts("PASS: casemap hashes agree for 129 lengths at 16 byte offsets");
}
