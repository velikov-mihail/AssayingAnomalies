function mycond = condmean(y, ytri, bi, bs)
% PURPOSE: This function computes the means of y in the classes determined by 
% the bounds bi and bs
%--------------------------------------------------------------
% USAGE: mycond = condmean(y, ytri, bi, bs)
%   where:   y =  nx1 vector of the unsorted initial values
%            ytri = nx1 vector of the indices of the ranked initial values
%            bi = indices of the inferior edges of the classes
%            bs = indices of the superior edges of the classes
%--------------------------------------------------------------
% OUTPUTS: mycond = conditional mean
%--------------------------------------------------------------
% used in sirmap.m
%------------------------------------------------------------------------
% Yves Aragon, June 2003
% Université de Toulouse I, Toulouse, France
% cthomas@cict.fr

n = length(bi);
%indice de la classe i 
for i = 1:n
  b = ytri(bi(i):bs(i),1);
 if i == 1
   a = mean(y(b,:));
 else
   a = [a ; mean(y(b,:))];
 end
end
mycond = a;



