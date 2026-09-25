'use client';

import {useEffect, useRef, useState} from 'react';
import {transliterateRomanToken} from '../../lib/hindiTransliteration';

export default function HindiPhoneticInput({defaultValue = '', value: controlledValue, hindiMode, onCommit, onValueChange, onKeyDown, ...props}) {
  const [value, setValue] = useState(String(defaultValue));
  const tokenStart = useRef(null);
  const currentValue = controlledValue === undefined ? value : String(controlledValue);

  useEffect(() => {
    if (controlledValue === undefined) setValue(String(defaultValue));
  }, [controlledValue, defaultValue]);

  function setNextValue(next) {
    if (controlledValue === undefined) setValue(next);
    onValueChange?.(next);
  }

  function replaceToken(element, appendSpace = false) {
    const start = tokenStart.current;
    const cursor = element.selectionStart ?? currentValue.length;
    if (!hindiMode || start === null || cursor <= start) return currentValue;
    const token = currentValue.slice(start, cursor);
    const converted = transliterateRomanToken(token);
    tokenStart.current = null;
    if (converted === token) return currentValue;
    const next = `${currentValue.slice(0, start)}${converted}${appendSpace ? ' ' : ''}${currentValue.slice(element.selectionEnd ?? cursor)}`;
    setNextValue(next);
    requestAnimationFrame(() => element.setSelectionRange(start + converted.length + (appendSpace ? 1 : 0), start + converted.length + (appendSpace ? 1 : 0)));
    return next;
  }

  function handleKeyDown(event) {
    onKeyDown?.(event);
    if (event.defaultPrevented || !hindiMode || event.ctrlKey || event.metaKey || event.altKey) return;
    const input = event.currentTarget;
    if (/^[a-z]$/i.test(event.key)) {
      if (tokenStart.current === null) tokenStart.current = input.selectionStart ?? currentValue.length;
      return;
    }
    if (event.key === ' ') {
      const next = replaceToken(input, true);
      if (next !== currentValue) event.preventDefault();
      return;
    }
    if (event.key === 'Backspace' || event.key === 'Delete' || event.key === 'Enter') tokenStart.current = null;
  }

  function handleBlur(event) {
    const next = replaceToken(event.currentTarget);
    if (next !== String(defaultValue)) onCommit?.(next);
  }

  return <input {...props} value={currentValue} onChange={event => setNextValue(event.target.value)} onKeyDown={handleKeyDown} onBlur={handleBlur} />;
}
