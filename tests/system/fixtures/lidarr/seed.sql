INSERT OR REPLACE INTO RootFolders (Id, Path, Name, DefaultMetadataProfileId, DefaultQualityProfileId)
VALUES (1, '/tmp/media', 'docker-test', 1, 1);

INSERT OR REPLACE INTO Tags (Id, Label) VALUES (1, 'test-tag');

INSERT OR REPLACE INTO ArtistMetadata (Id, ForeignArtistId, Name, Status, Images)
VALUES (1, '00000000-0000-0000-0000-000000000066', 'Test Artist', 1, '[]');

INSERT OR REPLACE INTO Artists (Id, CleanName, Path, Monitored, QualityProfileId, MetadataProfileId, ArtistMetadataId, MonitorNewItems)
VALUES (1, 'testartist', '/tmp/media/test-artist', 1, 1, 1, 1, 0);

INSERT OR REPLACE INTO Albums (Id, ForeignAlbumId, Title, CleanTitle, Images, Monitored, AlbumType, ArtistMetadataId, AnyReleaseOk, OldForeignAlbumIds, ReleaseDate)
VALUES
(1, '00000000-0000-0000-0000-000000000001', 'Test Album 01', 'testalbum01', '[]', 1, 'Album', 1, 1, '[]', '2020-01-01 00:00:00'),
(2, '00000000-0000-0000-0000-000000000002', 'Test Album 02', 'testalbum02', '[]', 1, 'Album', 1, 1, '[]', '2020-06-01 00:00:00'),
(3, '00000000-0000-0000-0000-000000000003', 'Test Album 03', 'testalbum03', '[]', 1, 'Album', 1, 1, '[]', '2021-01-01 00:00:00');

INSERT OR REPLACE INTO AlbumReleases (Id, ForeignReleaseId, AlbumId, Title, Status, Duration, Monitored, OldForeignReleaseIds)
VALUES
(1, '00000000-0000-0000-0001-000000000001', 1, 'Test Album 01', 'Official', 300000, 1, '[]'),
(2, '00000000-0000-0000-0002-000000000001', 2, 'Test Album 02', 'Official', 300000, 1, '[]'),
(3, '00000000-0000-0000-0003-000000000001', 3, 'Test Album 03', 'Official', 300000, 1, '[]');

INSERT OR REPLACE INTO Tracks (Id, ForeignTrackId, Title, Explicit, Duration, MediumNumber, AbsoluteTrackNumber, ForeignRecordingId, AlbumReleaseId, ArtistMetadataId, OldForeignRecordingIds, OldForeignTrackIds)
VALUES
(1, '00000000-0000-0000-0001-000000010001', 'Track 01', 0, 240000, 1, 1, '00000000-0000-0001-0001-000000000001', 1, 1, '[]', '[]'),
(2, '00000000-0000-0000-0002-000000010001', 'Track 01', 0, 240000, 1, 1, '00000000-0000-0002-0001-000000000001', 2, 1, '[]', '[]'),
(3, '00000000-0000-0000-0003-000000010001', 'Track 01', 0, 240000, 1, 1, '00000000-0000-0003-0001-000000000001', 3, 1, '[]', '[]');
