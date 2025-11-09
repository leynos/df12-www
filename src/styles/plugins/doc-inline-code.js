export default function docInlineCodePlugin({ addComponents }) {
  addComponents({
    ':root .doc-prose :where(code):not(:where(pre code))': {
      backgroundColor: 'rgb(229 231 235)',
      borderRadius: '0.25rem',
      borderColor: 'rgb(229 231 235)',
      borderStyle: 'solid',
      borderWidth: '0px',
      boxSizing: 'border-box',
      color: 'rgb(75 85 99)',
      fontFamily: 'var(--font-mono)',
      fontSize: 'var(--text-sm)',
      fontWeight: '400',
      letterSpacing: '-0.4px',
      lineHeight: 'var(--text-sm--line-height)',
      paddingBlock: '0.125rem',
      paddingInline: '0.25rem',
      tabSize: '4',
    },
  });
}
