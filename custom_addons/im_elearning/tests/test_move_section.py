from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import ImElearningCommon


@tagged('post_install', '-at_install')
class TestMoveSection(ImElearningCommon):
    """Moving lessons into another section."""

    def setUp(self):
        super().setUp()
        self.section_a = self._section('Recursion', 10)
        self.section_b = self._section('Further reading', 100)
        self.slides = self.env['slide.slide']
        for index in range(3):
            self.slides |= self.env['slide.slide'].create({
                'name': 'Lesson %s' % index,
                'channel_id': self.channel.id,
                'slide_category': 'article',
                'sequence': 101 + index,
            })

    def _section(self, name, sequence):
        return self.env['slide.slide'].create({
            'name': name, 'channel_id': self.channel.id,
            'is_category': True, 'sequence': sequence,
        })

    def _wizard(self, slides, section):
        return self.env['im.slide.move.section'].create({
            'slide_ids': [(6, 0, slides.ids)],
            'section_id': section.id if section else False,
        })

    def _sections_of(self, slides):
        return [slide.category_id for slide in slides]

    def test_moves_slides_into_target_section(self):
        self.assertEqual(self._sections_of(self.slides), [self.section_b] * 3)
        self._wizard(self.slides, self.section_a).action_move()
        self.slides.invalidate_recordset()
        self.assertEqual(self._sections_of(self.slides), [self.section_a] * 3)

    def test_keeps_relative_order(self):
        self._wizard(self.slides, self.section_a).action_move()
        self.slides.invalidate_recordset()
        ordered = self.slides.sorted('sequence').mapped('name')
        self.assertEqual(ordered, ['Lesson 0', 'Lesson 1', 'Lesson 2'])

    def test_other_sections_survive(self):
        """Inserting in the middle must not swallow the section behind it."""
        keeper = self.env['slide.slide'].create({
            'name': 'Lesson that stays', 'channel_id': self.channel.id,
            'slide_category': 'article', 'sequence': 200,
        })
        self._wizard(self.slides, self.section_a).action_move()
        keeper.invalidate_recordset()
        self.assertEqual(keeper.category_id, self.section_b)

    def test_empty_selection_raises(self):
        wizard = self.env['im.slide.move.section'].create({'slide_ids': [(6, 0, [])]})
        with self.assertRaises(UserError):
            wizard.action_move()

    def test_refuses_slides_from_two_courses(self):
        other = self.env['slide.channel'].create({'name': 'Another course'})
        stranger = self.env['slide.slide'].create({
            'name': 'Foreign lesson', 'channel_id': other.id,
            'slide_category': 'article'})
        wizard = self._wizard(self.slides | stranger, self.section_a)
        with self.assertRaises(UserError):
            wizard.action_move()

    def test_default_get_drops_section_headers(self):
        """A section header caught in the selection has to be dropped."""
        wizard = self.env['im.slide.move.section'].with_context(
            active_model='slide.slide',
            active_ids=(self.slides | self.section_b).ids,
        ).create({})
        self.assertNotIn(self.section_b, wizard.slide_ids)
        self.assertEqual(len(wizard.slide_ids), 3)

    def test_category_id_is_writable(self):
        """Set the section straight from the list rather than by dragging."""
        slide = self.slides[0]
        self.assertEqual(slide.category_id, self.section_b)

        slide.category_id = self.section_a
        slide.invalidate_recordset()

        self.assertEqual(slide.category_id, self.section_a)

    def test_multi_edit_moves_every_slide(self):
        """Select several rows and set the section once — the main use case."""
        self.slides.write({'category_id': self.section_a.id})
        self.slides.invalidate_recordset()
        self.assertEqual(self._sections_of(self.slides), [self.section_a] * 3)

    def test_writing_category_keeps_others_in_place(self):
        keeper = self.env['slide.slide'].create({
            'name': 'Lesson that stays', 'channel_id': self.channel.id,
            'slide_category': 'article', 'sequence': 300,
        })
        self.slides.write({'category_id': self.section_a.id})
        keeper.invalidate_recordset()
        self.assertEqual(keeper.category_id, self.section_b)

    def test_section_headers_are_not_moved(self):
        """Writing ``category_id`` onto a section header must do nothing."""
        before = self.section_b.sequence
        self.section_b.category_id = self.section_a
        self.section_b.invalidate_recordset()
        self.assertEqual(self.section_b.sequence, before,
                         "Dragging a section header away breaks the course "
                         "structure")
