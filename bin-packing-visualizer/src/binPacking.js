function binPacking(items, binCapacity) {
  const bins = [];

  items.forEach(item => {
    let placed = false;
    for (let i = 0; i < bins.length; i++) {
      if (bins[i].remainingCapacity >= item) {
        bins[i].items.push(item);
        bins[i].remainingCapacity -= item;
        placed = true;
        break;
      }
    }
    if (!placed) {
      bins.push({ items: [item], remainingCapacity: binCapacity - item, capacity: binCapacity });
    }
  });

  return bins;
}

export default binPacking;