type Props = {
  text: string;
};

export default function HelpTip({ text }: Props) {
  return (
    <span className="help-tip" title={text} aria-label={text}>
      ?
    </span>
  );
}

