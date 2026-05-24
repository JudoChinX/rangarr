INSERT OR REPLACE INTO RootFolders (Id, Path) VALUES (1, '/tmp/media');

INSERT OR REPLACE INTO Tags (Id, Label) VALUES (1, 'test-tag');

INSERT OR REPLACE INTO MovieMetadata (Id, ForeignId, MetadataSource, Images, Title, SortTitle, CleanTitle, OriginalLanguage, Status, Runtime, ReleaseDate, Year, Ratings, Genres, Recommendations, Credits, ItemType, StudioTitle)
VALUES
(1, 'scene-001', 0, '[]', 'Test Scene 01', 'test scene 01', 'testscene01', 1, 3, 30, '2024-01-15', 2024, '{}', '[]', '[]', '[]', 0, 'Test Studio One'),
(2, 'scene-002', 0, '[]', 'Test Scene 02', 'test scene 02', 'testscene02', 1, 3, 30, '2024-02-10', 2024, '{}', '[]', '[]', '[]', 0, 'Test Studio Two'),
(3, 'scene-003', 0, '[]', 'Test Scene 03', 'test scene 03', 'testscene03', 1, 3, 30, '2024-03-05', 2024, '{}', '[]', '[]', '[]', 0, 'Test Studio Three');

INSERT OR REPLACE INTO Movies (Id, Path, Monitored, QualityProfileId, MovieFileId, MovieMetadataId)
VALUES
(1, '/tmp/media/test-scene-01', 1, 1, 0, 1),
(2, '/tmp/media/test-scene-02', 1, 1, 0, 2),
(3, '/tmp/media/test-scene-03', 1, 1, 0, 3);
