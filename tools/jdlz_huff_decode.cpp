// jdlz_huff_decode <in.BIN> <out.tpk>:
// PC MINI_MAP*.BIN -> raw TPK stream
// Built by build.py

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iterator>
#include <new>
#include <string>
#include <vector>

#include "codex.h"
#include "huffcodex.h"

using Bytes = std::vector<uint8_t>;

static uint32_t Le32(const uint8_t* p)
{
    uint32_t v;
    memcpy(&v, p, 4);
    return v;
}

// Appends one JDLZ block to out; false on size mismatch.
static bool Jdlz(const uint8_t* in, size_t avail, Bytes& out)
{
    if (avail < 16 || memcmp(in, "JDLZ", 4) != 0) return false;

    const uint32_t usize = Le32(in + 8), csize = Le32(in + 12);
    if (csize > avail) return false;

    const size_t start = out.size();
    out.resize(start + usize);
    uint8_t* o = out.data() + start;

    size_t i = 16, n = 0;
    // Flag bytes, read bit by bit (0x100 marks when to reload): f1 picks
    // literal or back-reference, f2 the short or long reference form.
    uint32_t f1 = 1, f2 = 1;

    while (i < csize && n < usize) {
        if (f1 == 1) f1 = in[i++] | 0x100u;

        if (f2 == 1) {
            if (i >= csize) return false;
            f2 = in[i++] | 0x100u;
        }

        if (f1 & 1) {
            if (i + 2 > csize) return false;

            uint32_t length, distance;
            if (f2 & 1) {
                length = (in[i + 1] | ((in[i] & 0xF0u) << 4)) + 3;
                distance = (in[i] & 0x0Fu) + 1;

            } else {
                distance = (in[i + 1] | ((in[i] & 0xE0u) << 3)) + 17;
                length = (in[i] & 0x1Fu) + 3;
            }
            i += 2;

            if (distance > n) return false;
            for (uint32_t k = 0; k < length && n < usize; k++, n++)
                o[n] = o[n - distance];

            f2 >>= 1;

        } else {
            if (i >= csize) return false;
            o[n++] = in[i++];
        }

        f1 >>= 1;
    }

    return n == usize;
}

// Appends one HUFF block to out; false on size mismatch.
static bool Huff(const uint8_t* in, size_t avail, Bytes& out)
{
    if (avail < 16 || memcmp(in, "HUFF", 4) != 0) return false;

    const uint32_t usize = Le32(in + 8);
    const size_t start = out.size();

    // EA decoder has no input or output bounds (it ignores its
    // compressedsize argument); fine for our own trusted BINs.
    out.resize(start + usize + 256);  // decoder may write past the end
    const bool ok = HUFF_decode(&out[start], in + 16) == static_cast<int>(usize);
    out.resize(start + usize);

    return ok;
}

static std::string Format(const char* format, auto... args)
{
    char text[64];
    snprintf(text, sizeof(text), format, args...);
    return text;
}

// File = chunks: 0x3A100 (one JDLZ/HUFF block) or 0 (padding);
// blocks join in order.
static std::string Unpack(const Bytes& file, Bytes& out)
{
    size_t offset = 0;
    int block = 0;

    while (offset + 8 <= file.size()) {
        const uint32_t id = Le32(&file[offset]), size = Le32(&file[offset + 4]);
        if (offset + 8 + size > file.size())
            return Format("chunk at %zu runs past the end", offset);

        if (id == 0x3A100) {
            // Each checks size and magic before touching out.
            const uint8_t* in = &file[offset + 8];
            if (!Jdlz(in, size, out) && !Huff(in, size, out))
                return Format("block %d is not valid", block);
            block++;

        } else if (id != 0) {
            return Format("unknown chunk %08X at %zu", (unsigned)id, offset);
        }

        offset += 8 + size;
    }

    if (offset != file.size()) return "trailing bytes after the last chunk";
    if (out.size() < 4 || Le32(&out[0]) != 0xB3300000)  // TPK root chunk
        return "output is not a TPK stream";

    // Top-level chunk walk must end exactly at the stream end.
    size_t end = 0;
    while (end + 8 <= out.size()) {
        const size_t next = end + 8 + Le32(&out[end + 4]);
        if (next > out.size()) break;
        end = next;
    }

    if (end != out.size()) return "output chunks don't add up to its size";
    return {};
}

int main(int argc, char** argv)
{
    if (argc != 3) {
        fprintf(stderr, "usage: jdlz_huff_decode <in.BIN> <out.tpk>\n");
        return 1;
    }

    std::ifstream in(argv[1], std::ios::binary);
    if (!in) {
        fprintf(stderr, "%s: can't read\n", argv[1]);
        return 1;
    }

    const Bytes file((std::istreambuf_iterator<char>(in)), {});
    Bytes out;
    std::string error;

    // A corrupt size field can ask for more memory than there is.
    try {
        error = Unpack(file, out);
    } catch (const std::bad_alloc&) {
        error = "stated size is too large";
    }

    if (!error.empty()) {
        fprintf(stderr, "%s: %s\n", argv[1], error.c_str());
        return 1;
    }

    std::ofstream dst(argv[2], std::ios::binary);
    dst.write(reinterpret_cast<const char*>(out.data()), out.size());
    dst.close();

    if (!dst) {
        fprintf(stderr, "%s: can't write\n", argv[2]);
        return 1;
    }

    return 0;
}
