function [xindex, beta, valp]= sirf(x,y,nbcla)
% PURPOSE: SIR method for a unidimentional output (Sliced Inverse Regression)
%--------------------------------------------------------------
% USAGE: [xindex, beta, valp] = sirf(x,y,nbcla)
% where:   x =  explaining variable (matrix nxp)
%          y =  variable to explain (vector nx1)
%          nbcla = number of classes (integer)
%--------------------------------------------------------------
% OUTPUTS: xindex = indices = x'Beta (matrix nxp)
%          beta = vectors of edr direction (column) (matrix pxp)
%          valp = eigen values (vector px1)
%--------------------------------------------------------------
% written by Yves Aragon & Christine Thomas-Agnan (2002)
% Université de Toulouse I, Toulouse, France
% cthomas@cict.fr-

%--------------------------------------------------------------




[nobs , nvar] = size(x);


varx = cvarpds(x, ones(nobs,1));


%classes definition

[bi, bf] = numbcla(nobs, nbcla);

% sort y

[yt, ytri] = sort(y);


% compute the conditional means of x at the slices of y

my = condmean(y,ytri,bi,bf);


mxcond = condmean(x, ytri, bi, bf);

pds = bf - bi + ones(nbcla,1);

varmcond = cvarpds(mxcond, pds);


%Diagonalize

[beta, valp] = vprgen( varmcond, varx);





% beta's column are the EDR directions


xindex = x * beta;




