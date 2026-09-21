# H.A.R.A Site Front A — Issue #13 Live Evidence

Captured: `2026-09-21T03:41:05Z`

## Canonical identity

- Approved source: `brand/hara-capybara-flat-matte-source.png`
- Source SHA256: `17d877bf28825f172eca2371ccd046d0214c6c2268f05bfadf63b616b916b9d8`
- Active web asset: `public/assets/images/hara-brand-flat-matte.png`
- Active asset SHA256: `b65b11d97ed10a2cf5b00948d6e14520e4c8250b2ff6471d22d27db9f8d3efcc`
- Policy: flat/matte, non-mirrored, full capybara + triangle, `object-fit: contain`

## Git / CI

- Implementation PR: #17
- Merge SHA: `c9b7bbc3e2f7605dcf8bca3e4093c4abc19314ec`
- PR CI run `35558198206`: PASS
- main provenance run `35558224225`: PASS

## Cloudflare live readback

- `https://haralabs.com.br/`: HTTP 200; new brand references present
- `https://www.haralabs.com.br/`: HTTP 200; new brand references present
- Brand asset: HTTP 200 on both hosts, PNG 512x512, exact SHA `b65b11d9...8d3efcc`
- Apex/www asset parity: PASS
- Active legacy references in merged main: 0

## Screenshots

- `live-apex-home.png` — SHA256 `7c14e280cb7cf0eb0b05b373d8db89c2e1801af8219095f157e393ac5c816527`
- `live-apex-commander.png` — SHA256 `887a936c6ea276ba61fddb43afe4adf506e9f5423440cbbc74cef887d5b69bc0`
- `live-www-home.png` — SHA256 `4f37e851e9e2c4847790b66b218fe4a639559ad0fb2af1f9082fd8f4ac6bfb43`

`TECHNICAL_CLOSEOUT=PASS`

`OPERATOR_VISUAL_SIGNOFF=PENDING_OPERATOR_READBACK`
