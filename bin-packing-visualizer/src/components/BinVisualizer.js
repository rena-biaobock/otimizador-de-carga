import React, { useState, useEffect } from 'react';
// import binPacking from '../binPacking';

function BinVisualizer() {
  const [bins, setBins] = useState([]);
  const [items, setItems] = useState([5, 3, 8, 2, 9, 1, 4, 7, 6]);
  const [binCapacity, setBinCapacity] = useState(10);
  const [weightCol, setWeightCol] = useState('weight');

  // useEffect(() => {
  //   const packedBins = binPacking(items, binCapacity);
  //   setBins(packedBins);
  // }, [items, binCapacity]);

  const generateRandomItems = () => {
    const randomItems = Array.from({ length: 10 }, () => Math.floor(Math.random() * 9) + 1);
    setItems(randomItems);
  };

  const runAlgorithm = async () => {
    const data = {
      items: items.map(item => ({ weight: item })), // Map items to { weight: item } format
      capacity_kg: binCapacity,
      weight_col: weightCol,
    };

    const response = await fetch('http://localhost:5000/pack_loads', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(data),
    });

    const packedData = await response.json();
    setBins(packedData);
  };

  return (
    <div>
      <h2>Bin Visualization</h2>
      <div>
        <button onClick={runAlgorithm}>Run Algorithm</button>
      </div>
      {bins.map((bin, index) => (
        <div key={index} style={{ border: '1px solid black', margin: '10px', padding: '10px' }}>
          <h3>Bin {index + 1} (Capacity: {binCapacity})</h3>
          <p>Total Weight: {bin.load_total_weight}</p>
          <p>Items: {bin.items}</p>
        </div>
      ))}
    </div>
  );
}

export default BinVisualizer;