/**
 * Local ESLint rules.
 *
 * no-literal-ui-attribute: i18next/no-literal-string runs in "jsx-text-only"
 * mode (its "jsx-only" mode also flags every key, enum value and format
 * option inside JSX expressions). The attributes a user reads or hears —
 * aria-label, title, placeholder, alt, … — would slip through, so this rule
 * checks exactly those for literal strings. Allowed are the same patterns as
 * the text rule (symbols, numbers, abbreviations, product names).
 */

/** Attributes whose value is shown to or read out for the user. */
const UI_ATTRIBUTES = new Set([
  "aria-label",
  "aria-description",
  "aria-placeholder",
  "aria-roledescription",
  "aria-valuetext",
  "title",
  "placeholder",
  "alt",
  "label",
]);

/** Literal strings in an attribute value (also both branches of `a ? "x" : "y"`). */
function literals(node) {
  if (!node) return [];
  switch (node.type) {
    case "Literal":
      return typeof node.value === "string" ? [{ node, text: node.value }] : [];
    case "TemplateLiteral":
      return node.quasis.map((quasi) => ({ node: quasi, text: quasi.value.cooked ?? "" }));
    case "JSXExpressionContainer":
      return literals(node.expression);
    case "ConditionalExpression":
      return [...literals(node.consequent), ...literals(node.alternate)];
    case "LogicalExpression":
      return [...literals(node.left), ...literals(node.right)];
    default:
      return [];
  }
}

const noLiteralUiAttribute = {
  meta: {
    type: "problem",
    docs: { description: "Disallow untranslated literal strings in user-facing JSX attributes." },
    schema: [{ type: "object", properties: { allow: { type: "array", items: { type: "string" } } }, additionalProperties: false }],
    messages: { literal: "Untranslated text in {{attribute}}: use t() ({{text}})." },
  },
  create(context) {
    const allow = (context.options[0]?.allow ?? []).map((pattern) => new RegExp(`^(?:${pattern})$`, "u"));
    const allowed = (text) => !text.trim() || allow.some((pattern) => pattern.test(text.trim()));
    return {
      JSXAttribute(node) {
        const name = typeof node.name.name === "string" ? node.name.name : null;
        if (!name || !UI_ATTRIBUTES.has(name)) return;
        for (const { node: literal, text } of literals(node.value)) {
          if (!allowed(text)) context.report({ node: literal, messageId: "literal", data: { attribute: name, text: JSON.stringify(text) } });
        }
      },
    };
  },
};

export default { rules: { "no-literal-ui-attribute": noLiteralUiAttribute } };
