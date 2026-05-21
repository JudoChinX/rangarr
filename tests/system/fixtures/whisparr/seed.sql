INSERT OR REPLACE INTO RootFolders (Id, Path) VALUES (1, '/tmp/media');

INSERT OR REPLACE INTO Tags (Id, Label) VALUES (1, 'test-tag');

INSERT OR REPLACE INTO MovieMetadata (Id, ForeignId, MetadataSource, Images, Title, OriginalLanguage, Status, Runtime, Recommendations, Credits, ItemType)
VALUES
(1, 'whisparr-10001', 1, '[]', 'Test Scene 01', 1, 3, 30, '[]', '[]', 1),
(2, 'whisparr-10002', 1, '[]', 'Test Scene 02', 1, 3, 30, '[]', '[]', 1),
(3, 'whisparr-10003', 1, '[]', 'Test Scene 03', 1, 3, 30, '[]', '[]', 1);

INSERT OR REPLACE INTO Movies (Id, Path, Monitored, QualityProfileId, MovieFileId, MovieMetadataId)
VALUES
(1, '/tmp/media/test-scene-01', 1, 1, 0, 1),
(2, '/tmp/media/test-scene-02', 1, 1, 0, 2),
(3, '/tmp/media/test-scene-03', 1, 1, 0, 3);
