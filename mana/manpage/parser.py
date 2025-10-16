"""Man page parsing utilities."""
from __future__ import annotations


def extract_name_section(program: str, man_page_text: str) -> str:
    """Extract the NAME section from a man page as the semantic summary."""
    lines = man_page_text.split('\n')

    # Check if this is raw troff format (starts with . commands)
    is_troff = any(line.startswith('.') for line in lines[:20])

    if is_troff:
        # Parse troff format (.Sh NAME, .Nm, .Nd)
        in_name_section = False
        names = []
        description_parts = []

        for line in lines:
            stripped = line.strip()

            # Start of NAME section
            if stripped == '.Sh NAME':
                in_name_section = True
                continue

            # End of NAME section (next section)
            if in_name_section and stripped.startswith('.Sh '):
                break

            if in_name_section:
                # .Nm defines the name(s)
                if stripped.startswith('.Nm'):
                    name = stripped[3:].strip()
                    if name and name != program:  # Skip if it's just repeating program name
                        names.append(name)
                # .Nd is the description
                elif stripped.startswith('.Nd'):
                    description_parts.append(stripped[3:].strip())
                # Lines without macros might be continuation
                elif not stripped.startswith('.') and stripped:
                    description_parts.append(stripped)

        # Build description
        if description_parts:
            description = ' '.join(description_parts).strip()
        else:
            description = ''
    else:
        # Parse formatted text (old behavior)
        in_name_section = False
        name_lines = []

        for i, line in enumerate(lines):
            stripped = line.strip()

            # Detect NAME section header
            if stripped in ['NAME', 'N\x08NA\x08AM\x08ME\x08E']:
                in_name_section = True
                continue

            # If we're in NAME section
            if in_name_section:
                # Stop at next section header (all caps) or empty line after content
                if stripped and stripped.isupper() and len(stripped) > 3:
                    break
                if stripped:
                    name_lines.append(stripped)
                elif name_lines:  # Empty line after we've collected content
                    break

        # Join and clean up
        description = ' '.join(name_lines).strip()

        # Remove backspace characters
        result = []
        for char in description:
            if char == '\x08':
                if result:
                    result.pop()
            else:
                result.append(char)

        description = ''.join(result)

    # Fallback: if no NAME section found, use first substantial line
    if not description:
        for line in lines[:20]:
            stripped = line.strip()
            if stripped and len(stripped) > 20 and not stripped.isupper():
                description = stripped
                break

    return description if description else f"{program} - command-line utility"
