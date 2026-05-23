INSERT OR REPLACE INTO RootFolders (Id, Path, Name, DefaultMetadataProfileId, DefaultQualityProfileId, DefaultMonitorOption, DefaultTags, IsCalibreLibrary, DefaultNewItemMonitorOption)
VALUES (1, '/tmp/media', 'docker-test', 1, 1, 0, '[]', 0, 0);

INSERT OR REPLACE INTO Tags (Id, Label) VALUES (1, 'test-tag');

INSERT OR REPLACE INTO AuthorMetadata (Id, ForeignAuthorId, TitleSlug, Name, Status, Images, Aliases, SortName, NameLastFirst, SortNameLastFirst)
VALUES (1, '00000000-0000-0000-0000-000000000001', 'test-author-01', 'Test Author 01', 1, '[]', '[]', 'test author 01', 'Test Author 01', 'Author 01, Test');

INSERT OR REPLACE INTO Authors (Id, CleanName, Path, Monitored, QualityProfileId, MetadataProfileId, AuthorMetadataId, MonitorNewItems, Tags)
VALUES (1, 'testauthor01', '/tmp/media/test-author-01', 1, 1, 1, 1, 0, '[]');

INSERT OR REPLACE INTO Books (Id, AuthorMetadataId, ForeignBookId, TitleSlug, Title, CleanTitle, Monitored, AnyEditionOk, ReleaseDate, Links, Genres, Ratings, RelatedBooks)
VALUES
(1, 1, '00000000-0000-0000-0000-000000000101', 'test-book-01', 'Test Book 01', 'testbook01', 1, 1, '2020-01-01 00:00:00', '[]', '[]', '{}', '[]'),
(2, 1, '00000000-0000-0000-0000-000000000102', 'test-book-02', 'Test Book 02', 'testbook02', 1, 1, '2020-06-01 00:00:00', '[]', '[]', '{}', '[]'),
(3, 1, '00000000-0000-0000-0000-000000000103', 'test-book-03', 'Test Book 03', 'testbook03', 1, 1, '2021-01-01 00:00:00', '[]', '[]', '{}', '[]');

INSERT OR REPLACE INTO Editions (Id, BookId, ForeignEditionId, Title, TitleSlug, Images, Monitored, ManualAdd)
VALUES
(1, 1, '00000000-0000-0000-0001-000000000101', 'Test Book 01', 'test-book-01-edition', '[]', 1, 0),
(2, 2, '00000000-0000-0000-0001-000000000102', 'Test Book 02', 'test-book-02-edition', '[]', 1, 0),
(3, 3, '00000000-0000-0000-0001-000000000103', 'Test Book 03', 'test-book-03-edition', '[]', 1, 0);
