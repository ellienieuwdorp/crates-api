## 1.15.3-beta.1 - 2026-07-01

Compared with `1.15.1`.

### Summary

| Metric | Previous | Current | Delta |
| --- | ---: | ---: | ---: |
| Paths | 441 | 447 | +6 |
| Operations | 489 | 495 | +6 |
| Schemas | 141 | 141 | +0 |

### API Changes

- Added 6 operations.
- Removed 0 operations.
- Changed 8 operations.
- Added 0 schemas.
- Removed 0 schemas.
- Changed 1 schema.

### Added Operations

- `GET /backend/callback-owner`
- `POST /crates/update.batch`
- `POST /images/regenerate`
- `POST /sync/cancel`
- `POST /sync/export.decision`
- `POST /tunes/crates/preload`

### Changed Operations

- `DELETE /releases/{id}`
- `GET /crates/object`
- `GET /genius/verification`
- `GET /spotify/verification`
- `POST /playlists/import/public/{publicId}`
- `POST /tunes/crates/{crate_id}/add`
- `POST /tunes/crates/{crate_id}/remove`
- `PUT /audiofiles/relocate.all`

### Changed Schemas

- `ConfigurationSettings`
