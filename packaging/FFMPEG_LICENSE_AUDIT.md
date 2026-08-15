# FFmpeg external-component license audit

This document records reproducible facts about the pinned BtbN FFmpeg build.
It is an engineering audit, not legal advice or a declaration that the Release
is ready for redistribution.

## Fixed inputs

- FFmpeg build: `n8.1.2-34-g9b6c8969e0`
- BtbN build definition: `a99e8230eae00d1cee38f23076a7a1f55cd984e2`
- Binary and archive hashes: `ffmpeg-manifest.json`
- Direct configure-component inventory: `ffmpeg-components.json`
- Generated source-recipe inventory: `ffmpeg-build-recipes.json`

## Source inspection result

The source inventory was generated with:

```powershell
.\.venv\Scripts\python.exe scripts\audit_ffmpeg_component_licenses.py --fetch
```

At the 2026-08-15 inspection:

- 54 of 56 component entries were fetched at the exact 40-character Git
  revision recorded by the fixed BtbN build definition.
- LAME uses SourceForge SVN revision `6531` and needs a separate fixed-revision
  export and inspection path.
- Windows Schannel is a Windows system API rather than a bundled source Git
  repository and needs separate classification.
- The Git sources contained 198 filename-based license, notice, copyright, and
  patent candidates totaling about 1.1 MiB.
- Nine projects declared submodules. Some are test-only, while others may be
  compiled into a static library and therefore need separate review.
- The fixed BtbN recipes explicitly initialize nested sources for shaderc,
  libplacebo, JPEG XL's Highway dependency, librist's mbedTLS dependency, and
  zimg. Those nested sources are part of the remaining audit scope even when
  they do not appear as top-level FFmpeg `--enable-*` flags.
- Re-running BtbN's own `./generate.sh win64 lgpl 8.1` selected 77 source
  recipes containing 83 fixed source acquisitions. This exposed direct configure omissions (`chromaprint` and
  `ffnvcodec`) and transitive recipes including FFTW3, OpenSSL, libogg,
  libsamplerate, libudfread, libunibreak, Brotli, Little CMS, mbedTLS, and the
  LV2 support libraries.
- The 81 Git source acquisitions were fetched successfully. The three primary
  recipes expressed as
  tags were resolved to immutable commits and recorded in
  `ffmpeg-build-recipes.json`: OpenSSL `openssl-3.6.3`, Vulkan Headers
  `v1.4.356`, and mbedTLS `v4.1.0`. LAME remains the only SVN recipe.
- LAME's `COPYING` was obtained from the Subversion WebDAV revision-6531 path
  and pinned by SHA-256
  `e64f9c5a18f56828c10a575df13ade641aa3af4512a7afe6c411256943b57aaf`.
- Opus `autogen.sh` also downloads a non-VCS model archive pinned by SHA-256
  `a5177ec6fb7d15058e99e57029746100121f68e4890b1467d4094aa336b6013e`.
  The hash was verified against the complete 134,674,421-byte archive. DRED,
  Deep PLC, and OSCE remain disabled in the fixed build and extra programs are
  explicitly disabled, so none of that archive's model or generated DNN files
  are compiled or installed.
- Every one of the 82 fixed Git or SVN source acquisitions has at least one staged
  root notice. The version-controlled bundle contains 103 files with individual
  SHA-256 values in `ffmpeg-recipe-licenses.json`.
- Six additional fixed acquisitions exist beyond the recipes' primary source:
  five use `SCRIPT_REPO2/3` (gnulib, OpenCL ICD Loader, Vulkan Headers, and two
  alternate nv-codec-header revisions), while Opus downloads its model archive
  through `autogen.sh`. Their exact revisions and selection evidence are
  recorded in `ffmpeg-build-recipes.json` and
  `ffmpeg-additional-source-classification.json`. For FFmpeg 8.1 the sdk/13.0
  nv-codec-header checkout is selected; the primary and sdk/11.1 checkouts are
  not installed. libiconv uses its fixed gnulib checkout to regenerate build
  files and the separate `libicrt.a` used by the dependency's iconv command;
  FFmpeg links `libiconv.a`, and the dependency command is not copied into the
  BtbN archive. gnulib is therefore classified as a build tool rather than
  linked generated code, closing the additional-source review.
- `nv-codec-headers` has no standalone root license file. Its five installed
  headers contain two distinct MIT permission notices; both are preserved in
  the staged `HEADER-NOTICES.txt` with their source-header names.
The generated report and source checkouts live below `build/` and are ignored
by Git. They are evidence used to curate version-controlled notices; they are
not Release inputs.

## Why candidates are not copied automatically

A filename match alone cannot determine whether code was compiled into the
distributed executable. Several repositories contain licenses for tests,
examples, Debian packaging, vendored code, or optional build paths. Copying all
of them would be over-inclusive and could incorrectly imply that unrelated GPL
test code is part of the application.

Each candidate must therefore be checked against the fixed BtbN recipe and the
component's build configuration. Projects that download dependencies outside
Git submodules, such as shaderc's `git-sync-deps`, require an additional nested
dependency inventory.

Root-recipe notice collection, the explicit nested-source pass, and the
repository-internal vendored-code pass are complete for all 77 fixed recipes.
The inventories distinguish code linked into `ffmpeg.exe` from test-only,
disabled, unselected-provider, and build-tool dependencies.

The explicit nested-source pass now records 31 fixed revisions:

- 8 linked source dependencies;
- 1 dependency whose generated code is linked;
- 3 build-only tools;
- 19 test, demo, fuzz-data, or unselected-provider dependencies excluded from
  the installed static libraries.

All 31 fixed commits were fetched successfully. The 9 linked or
linked-generated entries have 12 staged root license files with hashes in
`ffmpeg-nested-licenses.json`. `ffmpeg-nested-dependencies.json` retains the
classification and build evidence for non-linked entries instead of mixing
their licenses into the binary distribution.

The vendored-code pass covers all 77 recipes: OpenAL, SDL, libopenmpt,
libiconv, Chromaprint, Game Music Emu, Kvazaar, libzmq, SVT-AV1, and VVenC. It
also covers zlib, libxml2, OpenSSL, oneVPL, AOM, libvpx, LCEVCdec, dav1d,
opencore-amr, OpenJPEG, SoXR, zimg, the six-recipe LV2/Lilv chain, FFTW3,
libsamplerate, libvorbis, libpng, libaribb24, libbluray, shaderc, libjxl, AMF,
libplacebo, HarfBuzz, librist, mbedTLS, libass, libwebp, VMAF, both Freetype
build passes, libogg, libopus, libtheora, XZ, FriBidi, GMP, libudfread,
libunibreak, Snappy, TwoLAME, uavs3d, OpenH264, OpenAPV, OpenCL, Vulkan
Headers, SPIR-V Headers, nv-codec-headers, libva, Brotli, Little CMS, SRT,
Fontconfig, libaribcaption, ZVBI, mingw-std-threads, Vulkan Shim Loader,
SPIRV-Cross, libssh, rav1e, LAME, and MinGW. The shaderc,
libplacebo, and mbedTLS linked sources remain tracked in the
nested-source manifest; the additional JPEG XL source-tree candidates are
disabled benchmark and development-tool helpers. The AMF recipe deletes its
entire `Thirdparty` tree before installing only the public headers.
HarfBuzz's compiled Microsoft USE-shaping data and embedded fasthash notice are
included explicitly. librist's win64 build selects bundled cJSON, LZ4, poll,
and time-shim code while using the separately built mbedTLS library. libass
adds the linked wyhash and mingw-w64 DirectWrite definitions; libwebp's only
separately licensed candidate is test-only. VMAF adds six linked third-party
code groups; the upstream `mkdirp.c` file only identifies MIT, so the complete
license is retained from fixed original revision
`4587acadbc304080b247aa4b2fc0b3d6ba1fe979`. Freetype's referenced FTL,
BDF, PCF, and embedded HarfBuzz notices are also retained; its final pass
replaces the bootstrap build and enables HarfBuzz integration. libtheora's
separate getopt copies are confined to disabled examples and legacy project
files. XZ's Crypto++-derived internal SHA-256 is compiled into liblzma under
0BSD; its command-tool getopt and helper scripts are outside the distributed
FFmpeg binary. FriBidi generates compiled bidi tables from its bundled Unicode
16.0.0 data, and libunibreak compiles committed tables derived from Unicode
data. Their source pointers are supplemented with the complete official
Unicode License V3 text retrieved from `https://www.unicode.org/license.txt`.
GMP's mini-gmp fallback, libudfread examples, and libunibreak tools and
conformance-test data are not selected by the fixed recipes. Snappy's test
submodules and corpus, uavs3d's non-installed decoder app, OpenH264's test and
console paths, and OpenAPV's disabled app/tests are likewise excluded. The
TwoLAME library does compile LAME- and tooLAME-derived routines under its root
LGPL terms, so its contributor and derivation record in `AUTHORS` is retained.
Vulkan's installed headers are dual Apache-2.0/MIT and the MIT text is staged;
its generators and SPIR-V's JsonCpp/test/documentation paths do not enter the
binary. The win64 libva build compiles the Microsoft/Emil Velikov display
implementation, whose retained MIT notice is included explicitly. OpenCL
build/test helpers are excluded, and the selected nv-codec header revision is
already covered by its installed-header notices. The vendored-code inventory
also excludes Brotli's non-C/test trees and Little CMS's separately built GPLv3
plugin archives; neither is linked into `ffmpeg.exe` or copied into the portable
distribution. SRT contributes four retained non-MPL notice groups: its
UDT-derived BSD core, public-domain atomic and endian helpers, and the Aladdin
MD5 implementation. Fontconfig contributes its public-domain MD5 implementation
and FreeType glue while its disabled tools and configuration assets are
excluded. libaribcaption's OpenSSL-selected build excludes its Openwall MD5
fallback, Android-only TinyXML2, tests, and embedded FreeType. ZVBI links its
AleVT-derived decoder and search code; disabled VTX code and Linux capture
compatibility paths are excluded. The installed mingw-std-threads headers are
covered by their BSD-2-Clause notice. Vulkan Shim Loader's generated registry
content is covered by the selected MIT branch of Vulkan-Headers' dual license,
and SPIRV-Cross's generated Khronos headers are covered by their MIT notice.

libssh links OpenSSH-derived code, OpenBSD bcrypt/Blowfish code, libcrux ML-KEM,
and public-domain sntrup code; unused provider fallbacks, tools, and tests are
excluded. rav1e's top-level linked x86 assembly helper retains its x264-derived
ISC-style notice, separately from the Cargo dependency inventory below. The
exact LAME SVN revision 6531 library tree was obtained from SourceForge's fixed
revision WebDAV endpoint. Its ReplayGain analysis and Ron Mayer-derived FFT
notices are retained; the frontend and decoder are excluded, and the x86_64
configuration sets `CPUTYPE=no`, so the legacy 32-bit GOGO-derived NASM files
are not built. MinGW's static winpthreads build is covered by its MIT and
Lockless BSD notices; the linked CRT also retains its public-domain disclaimer,
Lucent gdtoa notice, and BSD/Sun compatibility notices.

The inventory records 63 linked entries, 79 excluded paths, and 1 build-only
dependency in `ffmpeg-vendored-code.json`, and stages 72 notices with hashes in
`ffmpeg-vendored-licenses.json`. The staged notices include the complete
embedded fasthash notice by retaining `hb-algs.hh`. The classification follows the exact BtbN
options—for example, libopenmpt selects minimp3, libzmq selects wepoll, and
VVenC selects nlohmann-json, while their unselected alternatives and disabled
test/app dependencies remain excluded. The complete 77-recipe source-tree
candidate pass is closed and `vendored_code_review_complete` is `true`.
`release_ready` remains `false` until the remaining overall release gates are
closed.

rav1e's separate Cargo dependency pass is recorded, but its exact build lock
still cannot be attested. Its fixed source revision has 272 entries in
`Cargo.lock`, and BtbN runs
`cargo update cc` immediately before `cargo cinstall`. The public Actions log for
the 2026-07-31 build has expired (GitHub returns HTTP 410), so the exact resolved
lockfile cannot be read back from the build log. The build began after `cc 1.4.0`
was published and before any later compatible version; reconstructing the recipe
with `cargo update -p cc --precise 1.4.0` changes `cc` from 1.2.26 to 1.4.0 and
adds `find-msvc-tools` 0.1.11 and `shlex` 2.0.1. This is strong reconstruction
evidence, not an archived build attestation. Projecting the reconstructed graph
onto the win64 C API static library features identifies 42 linked candidates and
55 build-only packages. All linked candidates declare permissive licenses and
have 80 staged Cargo notice files in `rav1e-cargo-licenses`; the one crate archive that
omits its repository-root texts (`profiling` 1.0.16) is supplemented from the
crate's fixed VCS revision with source URLs and hashes. `rav1e-Cargo.lock` and
`rav1e-cargo-licenses.json` preserve the reconstructed graph.

The distributed `ffmpeg.exe` also contains
`rustc/8bab26f4f68e0e26f0bb7960be334d5b520ea452`, identifying Rust 1.97.1,
plus standard-library paths for `addr2line` 0.25.1, `gimli` 0.32.3, `object`
0.37.3, and `rustc-demangle` 0.1.27. These toolchain-linked objects are outside
rav1e's Cargo lock. The official x86_64-pc-windows-gnu rustc archive was checked
against its published SHA-256, and its standard-library copyright report plus
four applicable notice files are staged, bringing the rav1e bundle to 85 files.
Release remains blocked because the expired Actions log prevents attesting the
reconstructed Cargo graph as the exact build lockfile, and because the `cargo-c`
build-tool version was not pinned by BtbN.

## Release gate

The component, recipe, nested-source, vendored-code, and rav1e Cargo manifests
intentionally keep `release_ready` set to `false` while any overall release
gate remains open. The vendored-code review itself is complete; the remaining
gates include exact rav1e build-lock attestation, the unpinned `cargo-c` build
tool, corresponding-source references, and final Release-asset verification.
`scripts/build_release.ps1` refuses to produce Release assets while that value
is false. The gate may be changed only after required notices, license texts,
corresponding-source references, and nested compiled dependencies have been
reviewed and included in the portable `LICENSES/` directory.
