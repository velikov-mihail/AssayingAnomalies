function [ind]=Ilocal(variable,W)
%  PURPOSE:This function computes local Moran indices
%----------------- -----------------------------------------------------
%  USAGE: ind = Ilocal(variable,W)
%     where: variable : (n x 1) variable to study
%         W : (n x n ) contiguity matrix
%------------------- ---------------------------------------------------
%  OUTPUTS :  ind = local Moran indices
%-----------------------------------------------------------------------
%------------------------------------------------------------------------
% Christine Thomas-Agnan, Anne Ruiz-Gazen, Julien Moutel
% June 2003
% Université de Toulouse I, Toulouse, France
% cthomas@cict.fr


varc=zeros(length(variable),1);
vect=zeros(length(variable),1);
varc=variable-mean(variable); % centered variable 

ind=varc.*(W*varc);