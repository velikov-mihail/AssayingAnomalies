function [v, d] = vprgen(a,b)
% PURPOSE: Eigenvalues of the problem max(x'ax / x'bx) 
%--------------------------------------------------------------
% USAGE: [v, d] = vprgen(a,b)
%   where:   a =  matrix that appears in the numerator
%            b =  matrix that appears in the denominator
%--------------------------------------------------------------
% OUTPUTS: v = matrix of the eigenvectors
%          d = sorted eigenvalues (from the maximun to the minimum)
%--------------------------------------------------------------
%------------------------------------------------------------------------
% Yves Aragon, June 2003
% Université de Toulouse I, Toulouse, France
% cthomas@cict.fr



r = chol(b);
rm1 = inv(r);
a1 = rm1'*a*rm1;
[v, d] = eig(a1);
u = v * d * v' - a1;
v = rm1 * v;
d = diag(d);
[d1, i] = sort(d);
v = v(:,i);
d = d(i);
d = flipud(d);
v = fliplr(v);
