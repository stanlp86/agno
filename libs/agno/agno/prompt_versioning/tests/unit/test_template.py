"""
Unit tests for PromptTemplate.

Tests cover:
- Variable extraction from content
- Full rendering with all variables
- Partial rendering with subset of variables
- Variable validation
- Edge cases (empty, special characters, nested braces)
"""

import pytest
from agno.prompt_versioning.models import PromptTemplate


class TestVariableExtraction:
    """Tests for automatic variable extraction from template content."""

    def test_single_variable(self):
        """Extract single variable."""
        template = PromptTemplate(content="Hello, {{name}}!")
        assert template.variables == {"name"}

    def test_multiple_variables(self):
        """Extract multiple distinct variables."""
        template = PromptTemplate(content="{{greeting}}, {{name}}! Welcome to {{place}}.")
        assert template.variables == {"greeting", "name", "place"}

    def test_repeated_variable(self):
        """Repeated variable appears once in set."""
        template = PromptTemplate(content="{{name}} said hello. {{name}} waved.")
        assert template.variables == {"name"}

    def test_no_variables(self):
        """Template with no variables has empty set."""
        template = PromptTemplate(content="This is static text.")
        assert template.variables == set()

    def test_underscore_in_variable(self):
        """Variables can contain underscores."""
        template = PromptTemplate(content="{{first_name}} {{last_name}}")
        assert template.variables == {"first_name", "last_name"}

    def test_numbers_in_variable(self):
        """Variables can contain numbers (not at start)."""
        template = PromptTemplate(content="{{var1}} {{var2}}")
        assert template.variables == {"var1", "var2"}

    def test_multiline_content(self):
        """Extract variables from multiline content."""
        template = PromptTemplate(
            content="""
            Dear {{name}},

            Your order {{order_id}} is ready.

            Thanks,
            {{company}}
            """
        )
        assert template.variables == {"name", "order_id", "company"}

    def test_adjacent_variables(self):
        """Extract adjacent variables without space."""
        template = PromptTemplate(content="{{first}}{{last}}")
        assert template.variables == {"first", "last"}

    def test_variable_at_boundaries(self):
        """Variables at start and end of content."""
        template = PromptTemplate(content="{{start}} middle {{end}}")
        assert template.variables == {"start", "end"}


class TestRendering:
    """Tests for template rendering with variable substitution."""

    def test_render_single_variable(self):
        """Render with single variable."""
        template = PromptTemplate(content="Hello, {{name}}!")
        result = template.render(name="Alice")
        assert result == "Hello, Alice!"

    def test_render_multiple_variables(self):
        """Render with multiple variables."""
        template = PromptTemplate(content="{{greeting}}, {{name}}!")
        result = template.render(greeting="Hi", name="Bob")
        assert result == "Hi, Bob!"

    def test_render_repeated_variable(self):
        """Repeated variable is substituted everywhere."""
        template = PromptTemplate(content="{{name}} is {{name}}.")
        result = template.render(name="Alice")
        assert result == "Alice is Alice."

    def test_render_multiline(self):
        """Render multiline template."""
        template = PromptTemplate(content="Name: {{name}}\nAge: {{age}}")
        result = template.render(name="Alice", age="30")
        assert result == "Name: Alice\nAge: 30"

    def test_render_with_special_characters_in_value(self):
        """Values can contain special characters."""
        template = PromptTemplate(content="Message: {{msg}}")
        result = template.render(msg="Hello! @#$%^&*()")
        assert result == "Message: Hello! @#$%^&*()"

    def test_render_with_braces_in_value(self):
        """Values can contain braces."""
        template = PromptTemplate(content="Code: {{code}}")
        result = template.render(code="if (x) { return y; }")
        assert result == "Code: if (x) { return y; }"

    def test_render_empty_value(self):
        """Empty string is valid value."""
        template = PromptTemplate(content="Name: {{name}}")
        result = template.render(name="")
        assert result == "Name: "

    def test_render_numeric_value(self):
        """Numeric values are converted to strings."""
        template = PromptTemplate(content="Count: {{count}}")
        result = template.render(count=42)
        assert result == "Count: 42"

    def test_render_no_variables(self):
        """Render template with no variables."""
        template = PromptTemplate(content="Static text.")
        result = template.render()
        assert result == "Static text."


class TestRenderingErrors:
    """Tests for rendering error conditions."""

    def test_missing_single_variable(self):
        """Error when required variable missing."""
        template = PromptTemplate(content="Hello, {{name}}!")
        with pytest.raises(ValueError) as exc_info:
            template.render()
        assert "name" in str(exc_info.value)

    def test_missing_one_of_multiple(self):
        """Error lists all missing variables."""
        template = PromptTemplate(content="{{a}} {{b}} {{c}}")
        with pytest.raises(ValueError) as exc_info:
            template.render(a="A")
        error_msg = str(exc_info.value)
        assert "b" in error_msg or "c" in error_msg

    def test_extra_variables_ignored(self):
        """Extra variables are silently ignored."""
        template = PromptTemplate(content="Hello, {{name}}!")
        result = template.render(name="Alice", extra="ignored", another="also_ignored")
        assert result == "Hello, Alice!"


class TestPartialRendering:
    """Tests for partial template rendering."""

    def test_partial_render_some_variables(self):
        """Partial render substitutes only provided variables."""
        template = PromptTemplate(content="{{greeting}}, {{name}}!")
        partial = template.partial_render(greeting="Hello")
        assert partial.content == "Hello, {{name}}!"
        assert partial.variables == {"name"}

    def test_partial_render_all_variables(self):
        """Partial render with all variables removes all placeholders."""
        template = PromptTemplate(content="{{greeting}}, {{name}}!")
        partial = template.partial_render(greeting="Hello", name="Alice")
        assert partial.content == "Hello, Alice!"
        assert partial.variables == set()

    def test_partial_render_no_variables(self):
        """Partial render with no variables returns copy."""
        template = PromptTemplate(content="{{greeting}}, {{name}}!")
        partial = template.partial_render()
        assert partial.content == template.content
        assert partial.variables == template.variables

    def test_partial_render_unknown_variables(self):
        """Unknown variables in partial render are ignored."""
        template = PromptTemplate(content="Hello, {{name}}!")
        partial = template.partial_render(unknown="value")
        assert partial.content == "Hello, {{name}}!"

    def test_partial_render_chain(self):
        """Chain multiple partial renders."""
        template = PromptTemplate(content="{{a}} {{b}} {{c}}")
        step1 = template.partial_render(a="A")
        step2 = step1.partial_render(b="B")
        step3 = step2.partial_render(c="C")
        assert step3.content == "A B C"
        assert step3.variables == set()


class TestVariableValidation:
    """Tests for variable validation."""

    def test_validate_exact_match(self):
        """Validation passes with exact variable match."""
        template = PromptTemplate(content="{{a}} {{b}}")
        assert template.validate_variables({"a", "b"}) is True

    def test_validate_subset(self):
        """Validation passes when required is subset."""
        template = PromptTemplate(content="{{a}} {{b}} {{c}}")
        assert template.validate_variables({"a", "b"}) is True

    def test_validate_superset_fails(self):
        """Validation fails when required has extra vars."""
        template = PromptTemplate(content="{{a}} {{b}}")
        assert template.validate_variables({"a", "b", "c"}) is False

    def test_validate_empty_required(self):
        """Empty required set always passes."""
        template = PromptTemplate(content="{{a}} {{b}}")
        assert template.validate_variables(set()) is True

    def test_validate_no_template_vars(self):
        """No template vars, empty required passes."""
        template = PromptTemplate(content="Static")
        assert template.validate_variables(set()) is True
        assert template.validate_variables({"a"}) is False


class TestEdgeCases:
    """Tests for edge cases and special patterns."""

    def test_single_braces_not_variable(self):
        """Single braces are not treated as variables."""
        template = PromptTemplate(content="{name} is not {{name}}")
        assert template.variables == {"name"}

    def test_triple_braces(self):
        """Triple braces extract inner variable."""
        template = PromptTemplate(content="{{{name}}}")
        # This matches {{name}} inside the outer braces
        assert "name" in template.variables

    def test_empty_braces(self):
        """Empty braces are not variables."""
        template = PromptTemplate(content="Hello {{}} world")
        assert template.variables == set()

    def test_whitespace_in_braces(self):
        """Whitespace in braces doesn't match."""
        template = PromptTemplate(content="{{ name }}")
        assert template.variables == set()  # No match due to spaces

    def test_very_long_variable_name(self):
        """Long variable names are extracted."""
        long_name = "very_long_variable_name_that_goes_on_and_on"
        template = PromptTemplate(content=f"{{{{{long_name}}}}}")
        assert template.variables == {long_name}

    def test_unicode_content(self):
        """Unicode content is handled."""
        template = PromptTemplate(content="こんにちは、{{name}}さん!")
        assert template.variables == {"name"}
        result = template.render(name="田中")
        assert result == "こんにちは、田中さん!"

    def test_newlines_in_content(self):
        """Various newline styles work."""
        template = PromptTemplate(content="{{a}}\n{{b}}\r\n{{c}}")
        assert template.variables == {"a", "b", "c"}
