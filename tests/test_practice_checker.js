const assert = require('assert');
const { check } = require('../assets/practice-checker.js');
assert.equal(check('a  \r\nb\n', 'a\nb', {mode:'exact'}).verdict, 'pass');
assert.equal(check('a b', 'a\nb', {mode:'exact'}).verdict, 'fail');
assert.equal(check('1  2\n3', '1\n2 3', {mode:'tokens'}).verdict, 'pass');
assert.equal(check('2 1', '1 2', {mode:'tokens'}).verdict, 'fail');
assert.equal(check('1000000000000000001', '1000000000000000000', {mode:'tokens'}).verdict, 'fail');
assert.equal(check('1.0000001 2e-3', '1.0 0.002', {mode:'float', abs_tol:1e-6}).verdict, 'pass');
assert.equal(check('[0.8678 1.045]', '[0.8678 1.045 ]', {mode:'float', abs_tol:0.00005}).verdict, 'pass');
assert.equal(check('7.0;1.9400', '7;1.9400', {mode:'float', abs_tol:0.00005}).verdict, 'pass');
assert.equal(check('[1,2]', '[1 2]', {mode:'float', abs_tol:0.00005}).verdict, 'fail');
for (const value of ['NaN', 'Infinity', '1.01', '1.0 extra']) {
  assert.equal(check(value, '1.0', {mode:'float', abs_tol:1e-6}).verdict, 'fail');
}
assert.equal(check('{"b":[1,2],"a":true}', '{"a":true,"b":[1,2]}', {mode:'json'}).verdict, 'pass');
assert.equal(check('{"a":[2,1]}', '{"a":[1,2]}', {mode:'json'}).verdict, 'fail');
assert.equal(check('{"a":1,"x":2}', '{"a":1}', {mode:'json'}).verdict, 'fail');
assert.equal(check('{"a":1.00001}', '{"a":1}', {mode:'json',abs_tol:0.0001}).verdict, 'pass');
assert.equal(check('true', '1', {mode:'json'}).verdict, 'fail');
assert.equal(check('[]', '{}', {mode:'json'}).verdict, 'fail');
assert.equal(check('anything', 'example', {mode:'manual'}).verdict, 'review');
assert.equal(check('x', 'x', {mode:'unknown'}).verdict, 'review');
assert.equal(check('1010101', '0101010', {mode:'balanced-intervals'}, '7\n4\n1 4\n2 7\n3 6\n5 6').verdict, 'pass');
assert.equal(check('0011', '0101', {mode:'balanced-intervals'}, '4\n1\n1 4').verdict, 'pass');
assert.equal(check('0001', '0101', {mode:'balanced-intervals'}, '4\n1\n1 4').verdict, 'fail');
assert.equal(check('010', '', {mode:'balanced-intervals'}, '4\n1\n1 4').verdict, 'fail');
assert.equal(check('0101', '', {mode:'balanced-intervals'}, '4\n1\n1 9').verdict, 'review');
assert.equal(check('54\n1 3 4 2', '54\n2 4 3 1', {mode:'permutation-sum'}, '4').verdict, 'pass');
assert.equal(check('54\n1 2 3 4', '', {mode:'permutation-sum'}, '4').verdict, 'fail');
assert.equal(check('54\n2 4 4 1', '', {mode:'permutation-sum'}, '4').verdict, 'fail');
assert.equal(check('53\n1 3 4 2', '', {mode:'permutation-sum'}, '4').verdict, 'fail');
function permutations(values) {
  if(!values.length)return [[]];
  return values.flatMap((v,i)=>permutations(values.filter((_,j)=>i!==j)).map(rest=>[v,...rest]));
}
for(let n=1;n<=6;n++) {
  const candidates=permutations(Array.from({length:n},(_,i)=>i+1));
  const sums=candidates.map(p=>{
    let sum=0;
    for(let left=0;left<n;left++)for(let right=left;right<n;right++)sum+=p.slice(left,right+1).reduce((a,b)=>a+b,0);
    return sum;
  });
  const optimum=Math.max(...sums);
  candidates.forEach((p,i)=>assert.equal(check(optimum+'\n'+p.join(' '),'',{mode:'permutation-sum'},String(n)).verdict,sums[i]===optimum?'pass':'fail'));
}
for(let mask=0;mask<64;mask++) {
  const output=mask.toString(2).padStart(6,'0');
  const valid=output.slice(0,4).split('').filter(c=>c==='1').length===2 && output.slice(2,6).split('').filter(c=>c==='1').length===2;
  assert.equal(check(output,'',{mode:'balanced-intervals'},'6\n2\n1 4\n3 6').verdict,valid?'pass':'fail');
}
for(let x=1;x<=200;x++) {
  const sum = y=>String(y).split('').reduce((a,b)=>a+Number(b),0);
  const optimum=Math.max(...Array.from({length:x},(_,y)=>sum(y)));
  for(let y=0;y<x;y++) assert.equal(check(String(y),'',{mode:'max-digit-sum'},'1\n'+x).verdict,sum(y)===optimum?'pass':'fail');
  assert.equal(check(String(x),'',{mode:'max-digit-sum'},'1\n'+x).verdict,'fail');
}
assert.equal(check('19','28',{mode:'max-digit-sum'},'1\n29').verdict,'pass');
const reorder=[1,1,2,2,3];
for(let k=1;k<=5;k++) {
  const candidates=permutations(reorder);
  const valid = p=>p.every((_,i)=>new Set(p.slice(i,i+k)).size===p.slice(i,i+k).length);
  const input='5 '+k+'\n'+reorder.join(' ');
  candidates.forEach(p=>assert.equal(check(p.join(' '),'',{mode:'window-distinct'},input).verdict,valid(p)?'pass':'fail'));
  assert.equal(check('-1','',{mode:'window-distinct'},input).verdict,candidates.some(valid)?'fail':'pass');
}
assert.equal(check('1 2 3 4 1','1 2 1 3 4',{mode:'window-distinct'},'5 2\n1 1 2 3 4').verdict,'pass');
console.log('ACM checker behavior passed');
