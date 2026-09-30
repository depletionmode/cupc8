// Physical fitted cards determine passive bias, including cards whose firmware
// cannot boot. Firmware availability must not remove a soldered resistor.
export function fittedSlotWiring(runtime, slots, boardKind) {
  const links = runtime.card_slot_links;
  const signals = ['sck', 'mosi', 'cs', 'miso', 'irq'];
  if (!links || !['gpu', 'io', 'storage', 'wifi', 'eink'].every(kind =>
    signals.every(signal => typeof links[kind]?.[signal] === 'boolean')))
    throw new Error('machinenative: missing routed card slot links');
  let idle = runtime.miso_idle;
  const wiring = runtime.slots.map((mainLink, index) => {
    const installed = slots[index + 1];
    if (!installed) return mainLink;
    const kind = boardKind[installed];
    if (!kind) throw new Error(`machinenative: unknown installed card ${installed}`);
    const cardLink = links[kind];
    if (cardLink.miso_pulldown !== undefined && typeof cardLink.miso_pulldown !== 'boolean')
      throw new Error('machinenative: invalid card MISO pull-down');
    if (mainLink.miso_connected && cardLink.miso_pulldown === true) idle = 0;
    return { ...mainLink, ...Object.fromEntries(signals.map(signal =>
      [`${signal}_connected`, mainLink[`${signal}_connected`] && cardLink[signal]])) };
  });
  return { ...runtime, slots: wiring, miso_idle: idle };
}
