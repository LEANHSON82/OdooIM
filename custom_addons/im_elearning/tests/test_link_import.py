from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import ImElearningCommon

YT = 'https://www.youtube.com/watch?v='


@tagged('post_install', '-at_install')
class TestLinkImport(ImElearningCommon):
    """Bulk lesson import from a pasted list of links."""

    def _wizard(self, links, **kwargs):
        values = {'channel_id': self.channel.id, 'links': links,
                  'fetch_metadata': False}
        values.update(kwargs)
        return self.env['im.slide.link.import'].create(values)

    def _slides(self):
        return self.env['slide.slide'].search([
            ('channel_id', '=', self.channel.id),
            ('slide_category', '=', 'video'),
        ])

    def _section(self, name, sequence):
        return self.env['slide.slide'].create({
            'name': name, 'channel_id': self.channel.id,
            'is_category': True, 'sequence': sequence,
        })

    def test_creates_one_slide_per_line(self):
        self._wizard('\n'.join(YT + c * 11 for c in 'abc')).action_import()
        self.assertEqual(len(self._slides()), 3)

    def test_keeps_line_order(self):
        """Line order is lesson order, as the author arranged it."""
        links = '\n'.join('%s%s | Lesson %s' % (YT, c * 11, i)
                          for i, c in enumerate('abc', start=1))
        self._wizard(links).action_import()
        ordered = self._slides().sorted('sequence').mapped('name')
        self.assertEqual(ordered, ['Lesson 1', 'Lesson 2', 'Lesson 3'])

    def test_custom_title_after_pipe(self):
        self._wizard('%saaaaaaaaaaa | Sales process' % YT).action_import()
        self.assertEqual(self._slides().name, 'Sales process')

    def test_detects_video_source(self):
        self._wizard('%saaaaaaaaaaa' % YT).action_import()
        self.assertEqual(self._slides().video_source_type, 'youtube')

    def test_skips_blank_and_comment_lines(self):
        self._wizard('\n'.join([
            '# this is a note', '', '   ', '%saaaaaaaaaaa' % YT,
        ])).action_import()
        self.assertEqual(len(self._slides()), 1)

    def test_ignores_non_url_lines(self):
        self._wizard('\n'.join([
            'not a link at all', '%saaaaaaaaaaa' % YT,
        ])).action_import()
        self.assertEqual(len(self._slides()), 1)

    def test_deduplicates_within_the_list(self):
        link = '%saaaaaaaaaaa' % YT
        self._wizard('%s\n%s' % (link, link)).action_import()
        self.assertEqual(len(self._slides()), 1)

    def test_rerun_skips_existing(self):
        """Running again imports only what is missing, never a duplicate."""
        link = '%saaaaaaaaaaa' % YT
        self._wizard(link).action_import()
        wizard = self._wizard('%s\n%sbbbbbbbbbbb' % (link, YT))
        wizard.action_import()
        self.assertEqual(len(self._slides()), 2)
        self.assertIn('Bỏ qua 1', wizard.result)

    def test_empty_list_raises(self):
        with self.assertRaises(UserError):
            self._wizard('   \n  \n').action_import()

    def test_reports_created_count(self):
        wizard = self._wizard('\n'.join(YT + c * 11 for c in 'ab'))
        wizard.action_import()
        self.assertIn('2', wizard.result)

    def test_metadata_failure_does_not_abort_batch(self):
        """A missing Google API key is routine and must not fail the batch."""
        def boom(slide_self, image_url_only=False):
            raise ValueError('no api key')

        with patch.object(type(self.env['slide.slide']),
                          '_fetch_external_metadata', boom):
            wizard = self._wizard('\n'.join(YT + c * 11 for c in 'abc'),
                                  fetch_metadata=True)
            wizard.action_import()

        self.assertEqual(len(self._slides()), 3, "The lessons must still be created")
        self.assertIn('Cần xem lại', wizard.result, "And the problem must be reported")

    def test_metadata_does_not_override_custom_title(self):
        def meta(slide_self, image_url_only=False):
            return {'name': 'Title from YouTube'}, False

        with patch.object(type(self.env['slide.slide']),
                          '_fetch_external_metadata', meta):
            self._wizard('%saaaaaaaaaaa | My own title' % YT,
                         fetch_metadata=True).action_import()
        self.assertEqual(self._slides().name, 'My own title')

    def test_metadata_fills_missing_title(self):
        def meta(slide_self, image_url_only=False):
            return {'name': 'Title from YouTube', 'completion_time': 0.5}, False

        with patch.object(type(self.env['slide.slide']),
                          '_fetch_external_metadata', meta):
            self._wizard('%saaaaaaaaaaa' % YT, fetch_metadata=True).action_import()
        slide = self._slides()
        self.assertEqual(slide.name, 'Title from YouTube')
        self.assertEqual(slide.completion_time, 0.5)

    def test_imports_into_chosen_section(self):
        """Lessons land in the chosen section, not at the course end."""
        recursion = self._section('Recursion', 10)
        further = self._section('Further reading', 100)

        self._wizard('%saaaaaaaaaaa' % YT, section_id=recursion.id).action_import()

        slide = self._slides()
        self.assertEqual(len(slide), 1)
        self.assertEqual(
            slide.category_id, recursion,
            "Picking Recursion must put the lesson in Recursion, not %s"
            % further.name)

    def test_imports_after_existing_content_of_section(self):
        recursion = self._section('Recursion', 10)
        self.env['slide.slide'].create({
            'name': 'Existing lesson', 'channel_id': self.channel.id,
            'slide_category': 'article', 'sequence': 11,
        })
        self._section('Further reading', 100)

        self._wizard('%saaaaaaaaaaa | New lesson' % YT,
                     section_id=recursion.id).action_import()

        new = self._slides()
        self.assertEqual(new.category_id, recursion)
        self.assertGreater(new.sequence, 11,
                           "It must land after the section's existing lesson")

    def test_later_sections_are_pushed_down(self):
        """Inserting in the middle pushes later sections down."""
        recursion = self._section('Recursion', 10)
        further = self._section('Further reading', 20)
        last = self.env['slide.slide'].create({
            'name': 'Last lesson', 'channel_id': self.channel.id,
            'slide_category': 'article', 'sequence': 21,
        })

        self._wizard('\n'.join(YT + c * 11 for c in 'abc'),
                     section_id=recursion.id).action_import()

        last.invalidate_recordset()
        self.assertEqual(last.category_id, further,
                         "The last lesson must stay in its own section")
        for slide in self._slides():
            self.assertEqual(slide.category_id, recursion)

    def test_without_section_appends_to_end(self):
        self._section('Recursion', 10)
        further = self._section('Further reading', 100)
        self._wizard('%saaaaaaaaaaa' % YT).action_import()
        self.assertEqual(self._slides().category_id, further)

    def test_drive_links_do_not_all_become_view(self):
        """Drive links end in ``/view``, YouTube in ``/watch``."""
        links = '\n'.join([
            'https://drive.google.com/file/d/1AaAaAaAaAa/view',
            'https://drive.google.com/file/d/1BbBbBbBbBb/view?usp=sharing',
            'https://drive.google.com/file/d/1CcCcCcCcCc/view',
        ])
        self._wizard(links).action_import()

        names = self._slides().mapped('name')
        self.assertNotIn('view', names)
        self.assertEqual(len(set(names)), 3, "Every lesson needs its own name")

    def test_youtube_link_does_not_become_watch(self):
        self._wizard('%saaaaaaaaaaa' % YT).action_import()
        self.assertNotIn('watch', self._slides().mapped('name'))

    def test_readable_tail_is_kept(self):
        """A meaningful URL tail is still used as the title."""
        self._wizard('https://cdn.example.com/course/Opening_lesson').action_import()
        self.assertEqual(self._slides().name, 'Opening lesson')


@tagged('post_install', '-at_install')
class TestLinkImportSummary(ImElearningCommon):

    def test_summary_is_translatable(self):
        """The summary must go through env._; the module-level _ cannot find a
        language from a static method and Odoo logs a warning and skips it."""
        wizard = self.env['im.slide.link.import']
        with self.assertNoLogs('odoo.tools.translate', level='WARNING'):
            text = wizard._format_result(2, 1, ['https://example.test/a — lỗi'])
        self.assertIn('2', text)
        self.assertIn('1', text)
        self.assertIn('example.test', text)
