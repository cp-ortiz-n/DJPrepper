# Music Files and catalog flow

Music Files is the operational catalog workspace. Reads use a paginated
projection; mutations go through authoritative services that keep SQLite and
managed files consistent.

![Music Files and catalog flowchart](diagrams/music-files-and-catalog.svg)

## Read versus write ownership

| Concern                                               | Owner                                               |
| ----------------------------------------------------- | --------------------------------------------------- |
| Search, filters, pagination, stale-response rejection | `createRequestStateController()`                    |
| Catalog pages and facets                              | `DownloadedCatalogQueryService`                     |
| Audio, artwork, ZIP, download, and Finder reveal      | `DownloadedLibraryDeliveryService`                  |
| Analyze and reanalyze commands                        | `DownloadedTrackAnalysisQueue`                      |
| Metadata, genre, repair, and retag rules              | `TrackMetadataMutationService`                      |
| Bulk progress and retry                               | `MetadataBatchService` and `BatchOperationRegistry` |
| Recording/version relationships                       | `RecordingFamilyService`                            |
| Catalog/filesystem reconciliation                     | `LibraryMaintenanceService`                         |

## Mutation guarantee

A successful mutation updates the catalog, synchronizes relevant WAV tags or
sidecars, invalidates affected caches, republishes consumer projections, and
returns a visible receipt. If validation or file consistency fails, the service
refuses the operation instead of partially applying it.

## Identity levels

- Track ID: one cataloged file/version.
- Recording-family ID: versions of the same underlying song.
- File path: the current local asset location; relocation may change it.

Set Builder deduplicates at recording-family level while still allowing another
version to appear as an explicit alternative.

## Verification

Catalog, metadata, recording-family, and maintenance tests under
`tests/unit/library/` and `tests/unit/web/routes/`, plus Music Files browser
scenarios in `tests/browser/workflows.spec.js`.
